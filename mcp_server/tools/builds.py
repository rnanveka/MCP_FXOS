"""
Builds Tool - Trigger Jenkins pipeline builds.

This tool triggers builds on Jenkins pipelines:
- FXOS Precommit Bazel
- ASA Precommit Bazel

Features:
- Parameter validation
- Build status tracking
- Queue position reporting
"""

import os
import time
import logging
from typing import Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)


class BuildsTool:
    """MCP Tool for triggering Jenkins builds."""
    
    description = "Trigger a Jenkins pipeline build"
    
    parameters = {
        "pipeline": {
            "type": "string",
            "description": "Pipeline to build: FXOS_PB or ASA",
            "enum": ["FXOS_PB", "ASA"]
        },
        "branch": {
            "type": "string",
            "description": "Branch to build (e.g., main, fxos_2_19)"
        },
        "parameters": {
            "type": "object",
            "description": "Additional build parameters (optional)"
        }
    }
    
    required_params = ["pipeline", "branch"]
    
    # Pipeline configurations
    PIPELINES = {
        "FXOS_PB": {
            "name": "FXOS Precommit Bazel",
            "job_path_env": "JENKINS_JOB_PATH_FXOS_PB",
            "default_branch_param": "BRANCH"
        },
        "ASA": {
            "name": "ASA Precommit Bazel",
            "job_path_env": "JENKINS_JOB_PATH_ASA",
            "default_branch_param": "BRANCH"
        }
    }
    
    def __init__(self):
        self.jenkins_base = os.getenv("JENKINS_BASE_URL", "")
        self.jenkins_user = os.getenv("JENKINS_USER", "")
        self.jenkins_token = os.getenv("JENKINS_API_TOKEN", "")
        
        self._session = None
    
    @property
    def session(self) -> requests.Session:
        """Get authenticated requests session."""
        if self._session is None:
            self._session = requests.Session()
            self._session.auth = (self.jenkins_user, self.jenkins_token)
            self._session.headers.update({"Accept": "application/json"})
        return self._session
    
    def execute(
        self,
        pipeline: str,
        branch: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute the build trigger tool.
        
        Args:
            pipeline: Pipeline name (FXOS_PB or ASA)
            branch: Branch to build
            parameters: Optional additional build parameters
            
        Returns:
            Dict with build info and formatted output
        """
        pipeline = pipeline.upper()
        
        if pipeline not in self.PIPELINES:
            return {
                "error": f"Unknown pipeline: {pipeline}",
                "available_pipelines": list(self.PIPELINES.keys()),
                "formatted_output": f"❌ Unknown pipeline: {pipeline}"
            }
        
        config = self.PIPELINES[pipeline]
        job_path = os.getenv(config["job_path_env"], "")
        
        if not job_path:
            return {
                "error": f"Job path not configured for {pipeline}",
                "formatted_output": f"❌ Job path not configured for {pipeline}"
            }
        
        # Build parameters
        build_params = parameters.copy() if parameters else {}
        build_params[config["default_branch_param"]] = branch
        
        try:
            result = self._trigger_build(job_path, build_params)
            
            if result.get("success"):
                build_number = result.get("build_number")
                queue_id = result.get("queue_id")
                
                formatted = (
                    f"✅ **Build triggered successfully!**\n\n"
                    f"• **Pipeline:** {config['name']}\n"
                    f"• **Branch:** {branch}\n"
                )
                
                if build_number:
                    build_url = f"{self.jenkins_base.rstrip('/')}/{job_path.strip('/')}/{build_number}"
                    formatted += f"• **Build #:** [{build_number}]({build_url})"
                elif queue_id:
                    formatted += f"• **Queue ID:** {queue_id}\n"
                    formatted += "• Build is queued and will start shortly"
                
                return {
                    "success": True,
                    "pipeline": pipeline,
                    "branch": branch,
                    "build_number": build_number,
                    "queue_id": queue_id,
                    "formatted_output": formatted
                }
            else:
                error = result.get("error", "Unknown error")
                return {
                    "success": False,
                    "error": error,
                    "formatted_output": f"❌ Failed to trigger build: {error}"
                }
        
        except Exception as e:
            logger.exception(f"Error triggering build: {e}")
            return {
                "success": False,
                "error": str(e),
                "formatted_output": f"❌ Error triggering build: {e}"
            }
    
    def _trigger_build(self, job_path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trigger a Jenkins build.
        
        Args:
            job_path: Jenkins job path
            params: Build parameters
            
        Returns:
            Dict with build info or error
        """
        # Use buildWithParameters for parameterized builds
        build_url = f"{self.jenkins_base.rstrip('/')}/{job_path.strip('/')}/buildWithParameters"
        
        try:
            r = self.session.post(build_url, data=params, timeout=30)
            
            if r.status_code == 201:
                # Build queued successfully
                queue_location = r.headers.get("Location", "")
                queue_id = queue_location.split("/")[-2] if queue_location else None
                
                # Try to get build number from queue
                build_number = None
                if queue_id:
                    build_number = self._wait_for_build_number(queue_id)
                
                return {
                    "success": True,
                    "queue_id": queue_id,
                    "build_number": build_number
                }
            
            elif r.status_code == 200:
                # Some Jenkins configs return 200
                return {
                    "success": True,
                    "queue_id": None,
                    "build_number": None
                }
            
            else:
                return {
                    "success": False,
                    "error": f"HTTP {r.status_code}: {r.text[:200]}"
                }
        
        except requests.RequestException as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _wait_for_build_number(self, queue_id: str, timeout: int = 30) -> Optional[int]:
        """
        Wait for a queued build to get a build number.
        
        Args:
            queue_id: Jenkins queue item ID
            timeout: Maximum seconds to wait
            
        Returns:
            Build number or None
        """
        queue_url = f"{self.jenkins_base.rstrip('/')}/queue/item/{queue_id}/api/json"
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                r = self.session.get(queue_url, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    
                    # Check if build has started
                    executable = data.get("executable")
                    if executable:
                        return executable.get("number")
                    
                    # Still in queue
                    if data.get("blocked") or data.get("buildable"):
                        time.sleep(2)
                        continue
                
                break
            
            except requests.RequestException:
                break
        
        return None
    
    def get_build_status(self, pipeline: str, build_number: int) -> Dict[str, Any]:
        """
        Get the status of a specific build.
        
        Args:
            pipeline: Pipeline name
            build_number: Build number
            
        Returns:
            Dict with build status
        """
        if pipeline not in self.PIPELINES:
            return {"error": f"Unknown pipeline: {pipeline}"}
        
        config = self.PIPELINES[pipeline]
        job_path = os.getenv(config["job_path_env"], "")
        
        api_url = f"{self.jenkins_base.rstrip('/')}/{job_path.strip('/')}/{build_number}/api/json"
        
        try:
            r = self.session.get(api_url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                return {
                    "build_number": build_number,
                    "result": data.get("result"),
                    "building": data.get("building", False),
                    "duration": data.get("duration"),
                    "url": data.get("url")
                }
            else:
                return {"error": f"HTTP {r.status_code}"}
        
        except requests.RequestException as e:
            return {"error": str(e)}
