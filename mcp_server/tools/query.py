"""
Query Tool - Query Splunk for branch build status.

This tool queries Splunk for build information including:
- Make/Bazel build status
- Average build durations
- Review numbers and URLs
- Failure classification (Delta Change, Platform Failure, Intermittent)

Branches:
- fxos_19: FXOS 2.19 Main
- fxos_18: FXOS 2.18 Main
- lina/cairo: LINA Cairo branch
"""

import os
import time
import logging
from typing import Dict, Any, List, Optional

import requests

logger = logging.getLogger(__name__)


class QueryTool:
    """MCP Tool for querying Splunk branch status."""
    
    description = "Query Splunk for branch build status"
    
    parameters = {
        "branch": {
            "type": "string",
            "description": "Branch name: fxos_19, fxos_18, cairo, lina"
        }
    }
    
    required_params = ["branch"]
    
    # Branch configurations
    BRANCHES = {
        "fxos_19": {
            "name": "fxos_19",
            "project": "boreas",
            "splunk_filter": 'branch="uxbridge/FXOS_2_19_MAIN"',
            "display_name": "FXOS 2.19"
        },
        "fxos_18": {
            "name": "fxos_18",
            "project": "boreas",
            "splunk_filter": 'branch="temple/FXOS_2_18_MAIN"',
            "display_name": "FXOS 2.18"
        },
        "lina": {
            "name": "lina",
            "project": "lina",
            "splunk_filter": 'branch="cairo"',
            "display_name": "LINA Cairo"
        },
        "cairo": {  # Alias for lina
            "name": "cairo",
            "project": "lina",
            "splunk_filter": 'branch="cairo"',
            "display_name": "Cairo"
        }
    }
    
    def __init__(self):
        self.splunk_host = os.getenv("SPLUNK_HOST", "")
        self.splunk_token = os.getenv("SPLUNK_TOKEN", "")
        self.swarm_base = os.getenv("SWARM_BASE_URL", "")
        self.swarm_token = os.getenv("SWARM_API_TOKEN", "")
        self.jenkins_base = os.getenv("JENKINS_BASE_URL", "")
        self.jenkins_user = os.getenv("JENKINS_USER", "")
        self.jenkins_token = os.getenv("JENKINS_API_TOKEN", "")
    
    def execute(self, branch: str) -> Dict[str, Any]:
        """
        Execute the query tool for a specific branch.
        
        Args:
            branch: Branch name to query
            
        Returns:
            Dict with branch status and formatted output
        """
        branch_lower = branch.lower()
        
        if branch_lower not in self.BRANCHES:
            return {
                "error": f"Unknown branch: {branch}",
                "available_branches": list(self.BRANCHES.keys()),
                "formatted_output": f"❌ Unknown branch: {branch}\n\nAvailable: {', '.join(self.BRANCHES.keys())}"
            }
        
        config = self.BRANCHES[branch_lower]
        
        try:
            result = self._query_branch(config)
            formatted = self._format_branch_status(result)
            
            return {
                "branch": config["name"],
                "data": result,
                "formatted_output": formatted
            }
        
        except Exception as e:
            logger.exception(f"Error querying branch {branch}: {e}")
            return {
                "error": str(e),
                "formatted_output": f"❌ Error querying {branch}: {e}"
            }
    
    def list_failures(self) -> Dict[str, Any]:
        """
        List all failing branches.
        
        Returns:
            Dict with all branch statuses and failures
        """
        results = []
        failures = []
        
        for branch_key, config in self.BRANCHES.items():
            # Skip aliases
            if branch_key in ("cairo",):
                continue
            
            try:
                result = self._query_branch(config)
                results.append(result)
                
                if result.get("status") != "✅ SUCCESS":
                    failures.append(result)
            
            except Exception as e:
                logger.error(f"Error querying {branch_key}: {e}")
                failures.append({
                    "branch": config["name"],
                    "status": "❌ ERROR",
                    "error": str(e)
                })
        
        formatted = self._format_failures_list(failures)
        
        return {
            "total_branches": len(results),
            "failing_count": len(failures),
            "failures": failures,
            "formatted_output": formatted
        }
    
    def _query_branch(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Query Splunk for a branch's status."""
        branch_name = config["name"]
        splunk_filter = config["splunk_filter"]
        
        # Build Splunk search query
        search_query = f"""
        search index=ci_builds {splunk_filter} earliest=-24h
        | head 1
        | eval Review=Review
        | eval make_status=coalesce(make_result, "UNKNOWN")
        | eval bazel_status=coalesce(bazel_result, "UNKNOWN")
        | table Review, make_status, bazel_status, make_url, bazel_url, make_duration, bazel_duration
        """
        
        splunk_data = self._execute_splunk_search(search_query)
        
        if not splunk_data:
            return {
                "branch": branch_name,
                "display_name": config["display_name"],
                "status": "⚠️ NO DATA",
                "error": "No builds found in last 24h",
                "make_status": None,
                "bazel_status": None,
                "review": None
            }
        
        # Extract data
        review = splunk_data.get("Review", "")
        make_status = splunk_data.get("make_status", "UNKNOWN")
        bazel_status = splunk_data.get("bazel_status", "UNKNOWN")
        make_url = splunk_data.get("make_url", "")
        bazel_url = splunk_data.get("bazel_url", "")
        
        # Construct Swarm review URL
        review_url = f"https://sp4-fp-swarm.cisco.com/reviews/{review}" if review else ""
        
        base_result = {
            "branch": branch_name,
            "display_name": config["display_name"],
            "make_status": make_status,
            "bazel_status": bazel_status,
            "review": review,
            "review_url": review_url,
            "make_url": make_url,
            "bazel_url": bazel_url,
        }
        
        # Both SUCCESS
        if make_status == "SUCCESS" and bazel_status == "SUCCESS":
            return {
                **base_result,
                "status": "✅ SUCCESS",
                "error": None
            }
        
        # Check for delta change
        if review:
            is_delta = self._check_swarm_delta(review)
            if is_delta:
                return {
                    **base_result,
                    "status": "⚠️ DELTA CHANGE",
                    "error": "Makefile-only change (no .bazel/BUILD files)"
                }
        
        # Check Jenkins for error details
        failed_url = make_url if make_status != "SUCCESS" else bazel_url
        jenkins_error = self._check_jenkins_error(failed_url)
        
        if jenkins_error:
            return {
                **base_result,
                "status": "❌ PLATFORM FAILURE",
                "error": jenkins_error[:200]
            }
        
        # No specific error found
        return {
            **base_result,
            "status": "⚠️ INTERMITTENT",
            "error": "Build failed without specific error pattern"
        }
    
    def _execute_splunk_search(self, query: str) -> Optional[Dict[str, Any]]:
        """Execute a Splunk search and return results."""
        if not self.splunk_host or not self.splunk_token:
            logger.warning("Splunk credentials not configured")
            return None
        
        headers = {
            "Authorization": f"Bearer {self.splunk_token}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        try:
            # Create search job
            create_url = f"{self.splunk_host}/services/search/jobs"
            r = requests.post(
                create_url,
                headers=headers,
                data={"search": query, "output_mode": "json"},
                timeout=30,
                verify=False
            )
            
            if r.status_code != 201:
                logger.error(f"Splunk search creation failed: {r.status_code}")
                return None
            
            job_id = r.json().get("sid")
            
            # Wait for job completion
            results_url = f"{self.splunk_host}/services/search/jobs/{job_id}/results"
            for _ in range(30):  # 30 second timeout
                time.sleep(1)
                r = requests.get(
                    results_url,
                    headers=headers,
                    params={"output_mode": "json"},
                    timeout=10,
                    verify=False
                )
                
                if r.status_code == 200:
                    results = r.json().get("results", [])
                    return results[0] if results else None
            
            return None
        
        except requests.RequestException as e:
            logger.error(f"Splunk request failed: {e}")
            return None
    
    def _check_swarm_delta(self, review: str) -> bool:
        """Check if a review contains only Makefile changes (delta change)."""
        if not self.swarm_base or not self.swarm_token or not review:
            return False
        
        try:
            headers = {"Authorization": f"token {self.swarm_token}"}
            url = f"{self.swarm_base}/api/v9/reviews/{review}/files"
            
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                return False
            
            files = r.json().get("files", [])
            
            # Check if any files are bazel-related
            for f in files:
                path = f.get("depotFile", "").lower()
                if ".bazel" in path or "BUILD" in path or path.endswith(".bzl"):
                    return False
            
            # Only Makefile changes
            return True
        
        except requests.RequestException:
            return False
    
    def _check_jenkins_error(self, build_url: str) -> Optional[str]:
        """Check Jenkins for greperror artifact."""
        if not build_url or not self.jenkins_user or not self.jenkins_token:
            return None
        
        try:
            # Try to fetch greperror artifact
            error_url = f"{build_url}/artifact/greperror.txt"
            r = requests.get(
                error_url,
                auth=(self.jenkins_user, self.jenkins_token),
                timeout=10
            )
            
            if r.status_code == 200 and r.text.strip():
                return r.text.strip()
            
            return None
        
        except requests.RequestException:
            return None
    
    def _format_branch_status(self, result: Dict[str, Any]) -> str:
        """Format a single branch status for display."""
        branch = result.get("display_name", result.get("branch", "Unknown"))
        status = result.get("status", "Unknown")
        make_st = result.get("make_status", "—")
        bazel_st = result.get("bazel_status", "—")
        review = result.get("review", "")
        review_url = result.get("review_url", "")
        error = result.get("error", "")
        
        lines = [
            f"**{branch}** - {status}",
            "",
            f"• **Make:** {'✅' if make_st == 'SUCCESS' else '❌'} {make_st}",
            f"• **Bazel:** {'✅' if bazel_st == 'SUCCESS' else '❌'} {bazel_st}",
        ]
        
        if review:
            if review_url:
                lines.append(f"• **Review:** [CL#{review}]({review_url})")
            else:
                lines.append(f"• **Review:** CL#{review}")
        
        if error:
            lines.extend(["", f"**Error:** {error}"])
        
        return "\n".join(lines)
    
    def _format_failures_list(self, failures: List[Dict[str, Any]]) -> str:
        """Format failures list for display."""
        if not failures:
            return "✅ **All branches passing!**"
        
        lines = [
            f"❌ **{len(failures)} Branch(es) Failing**",
            ""
        ]
        
        for f in failures:
            branch = f.get("display_name", f.get("branch", "Unknown"))
            status = f.get("status", "")
            error = f.get("error", "")
            
            lines.append(f"• **{branch}**: {status}")
            if error:
                lines.append(f"  └─ {error[:100]}")
        
        return "\n".join(lines)
