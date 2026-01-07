"""
Splunk Client - MCP client for Splunk integration.

This client provides methods to interact with Splunk:
- Execute search queries
- Get build reports
- Analyze failure patterns
"""

import os
import time
import logging
from typing import Dict, Any, List, Optional

import requests

logger = logging.getLogger(__name__)


class SplunkClient:
    """Client for interacting with Splunk API."""
    
    def __init__(
        self,
        host: Optional[str] = None,
        token: Optional[str] = None
    ):
        """
        Initialize Splunk client.
        
        Args:
            host: Splunk host URL (falls back to env)
            token: Splunk API token (falls back to env)
        """
        self.host = host or os.getenv("SPLUNK_HOST", "")
        self.token = token or os.getenv("SPLUNK_TOKEN", "")
    
    def search(
        self,
        query: str,
        earliest: str = "-24h",
        latest: str = "now",
        timeout: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Execute a Splunk search.
        
        Args:
            query: Splunk search query (SPL)
            earliest: Earliest time for search
            latest: Latest time for search
            timeout: Maximum seconds to wait for results
            
        Returns:
            List of result dicts
        """
        if not self.host or not self.token:
            logger.warning("Splunk credentials not configured")
            return []
        
        # Create search job
        job_id = self._create_search_job(query, earliest, latest)
        if not job_id:
            return []
        
        # Wait for results
        results = self._wait_for_results(job_id, timeout)
        
        return results
    
    def _create_search_job(
        self,
        query: str,
        earliest: str,
        latest: str
    ) -> Optional[str]:
        """Create a Splunk search job."""
        url = f"{self.host}/services/search/jobs"
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "search": query,
            "earliest_time": earliest,
            "latest_time": latest,
            "output_mode": "json"
        }
        
        try:
            r = requests.post(url, headers=headers, data=data, timeout=30, verify=False)
            
            if r.status_code == 201:
                return r.json().get("sid")
            else:
                logger.error(f"Splunk job creation failed: {r.status_code}")
                return None
        
        except requests.RequestException as e:
            logger.error(f"Splunk request failed: {e}")
            return None
    
    def _wait_for_results(
        self,
        job_id: str,
        timeout: int
    ) -> List[Dict[str, Any]]:
        """Wait for search job to complete and return results."""
        results_url = f"{self.host}/services/search/jobs/{job_id}/results"
        status_url = f"{self.host}/services/search/jobs/{job_id}"
        
        headers = {
            "Authorization": f"Bearer {self.token}"
        }
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Check job status
                r = requests.get(
                    status_url,
                    headers=headers,
                    params={"output_mode": "json"},
                    timeout=10,
                    verify=False
                )
                
                if r.status_code != 200:
                    break
                
                status = r.json().get("entry", [{}])[0].get("content", {})
                
                if status.get("isDone"):
                    # Get results
                    r = requests.get(
                        results_url,
                        headers=headers,
                        params={"output_mode": "json", "count": 0},
                        timeout=30,
                        verify=False
                    )
                    
                    if r.status_code == 200:
                        return r.json().get("results", [])
                    break
                
                time.sleep(1)
            
            except requests.RequestException as e:
                logger.error(f"Error waiting for Splunk results: {e}")
                break
        
        return []
    
    def get_branch_status(self, branch_filter: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest build status for a branch.
        
        Args:
            branch_filter: Splunk filter for the branch
            
        Returns:
            Build status dict or None
        """
        query = f"""
        search index=ci_builds {branch_filter}
        | head 1
        | table Review, make_result, bazel_result, make_url, bazel_url
        """
        
        results = self.search(query)
        return results[0] if results else None
    
    def get_recent_builds(
        self,
        branch_filter: str,
        count: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get recent builds for a branch.
        
        Args:
            branch_filter: Splunk filter for the branch
            count: Number of builds to retrieve
            
        Returns:
            List of build dicts
        """
        query = f"""
        search index=ci_builds {branch_filter}
        | head {count}
        | table _time, Review, make_result, bazel_result, make_duration, bazel_duration
        """
        
        return self.search(query)
    
    def get_average_durations(
        self,
        branch_filter: str,
        days: int = 7
    ) -> Dict[str, Optional[float]]:
        """
        Get average build durations for a branch.
        
        Args:
            branch_filter: Splunk filter for the branch
            days: Number of days to average over
            
        Returns:
            Dict with avg_make_duration and avg_bazel_duration
        """
        query = f"""
        search index=ci_builds {branch_filter} earliest=-{days}d
        | where make_result="SUCCESS" AND bazel_result="SUCCESS"
        | stats avg(make_duration) as avg_make, avg(bazel_duration) as avg_bazel
        """
        
        results = self.search(query)
        
        if results:
            result = results[0]
            return {
                "avg_make_duration": self._safe_float(result.get("avg_make")),
                "avg_bazel_duration": self._safe_float(result.get("avg_bazel"))
            }
        
        return {"avg_make_duration": None, "avg_bazel_duration": None}
    
    def get_failure_rate(
        self,
        branch_filter: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get failure rate statistics for a branch.
        
        Args:
            branch_filter: Splunk filter for the branch
            days: Number of days to analyze
            
        Returns:
            Dict with failure statistics
        """
        query = f"""
        search index=ci_builds {branch_filter} earliest=-{days}d
        | stats count as total,
                sum(if(make_result="SUCCESS" AND bazel_result="SUCCESS", 1, 0)) as success,
                sum(if(make_result="FAILURE", 1, 0)) as make_failures,
                sum(if(bazel_result="FAILURE", 1, 0)) as bazel_failures
        | eval success_rate = round(success/total*100, 1)
        """
        
        results = self.search(query)
        
        if results:
            result = results[0]
            return {
                "total_builds": self._safe_int(result.get("total")),
                "successful": self._safe_int(result.get("success")),
                "make_failures": self._safe_int(result.get("make_failures")),
                "bazel_failures": self._safe_int(result.get("bazel_failures")),
                "success_rate": self._safe_float(result.get("success_rate"))
            }
        
        return {
            "total_builds": 0,
            "successful": 0,
            "make_failures": 0,
            "bazel_failures": 0,
            "success_rate": 0.0
        }
    
    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        """Safely convert value to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def _safe_int(value: Any) -> int:
        """Safely convert value to int."""
        if value is None:
            return 0
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return 0
