"""
Jenkins Client - MCP client for Jenkins integration.

This client provides methods to interact with Jenkins:
- Get build information
- Trigger builds
- Fetch artifacts
- Monitor build status
"""

import os
import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

import requests

logger = logging.getLogger(__name__)


class JenkinsClient:
    """Client for interacting with Jenkins API."""
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        user: Optional[str] = None,
        token: Optional[str] = None
    ):
        """
        Initialize Jenkins client.
        
        Args:
            base_url: Jenkins base URL (falls back to env)
            user: Jenkins username (falls back to env)
            token: Jenkins API token (falls back to env)
        """
        self.base_url = base_url or os.getenv("JENKINS_BASE_URL", "")
        self.user = user or os.getenv("JENKINS_USER", "")
        self.token = token or os.getenv("JENKINS_API_TOKEN", "")
        
        self._session = None
    
    @property
    def session(self) -> requests.Session:
        """Get authenticated requests session."""
        if self._session is None:
            self._session = requests.Session()
            self._session.auth = (self.user, self.token)
            self._session.headers.update({"Accept": "application/json"})
        return self._session
    
    def get_job_info(self, job_path: str) -> Dict[str, Any]:
        """
        Get information about a Jenkins job.
        
        Args:
            job_path: Path to the job (e.g., job/FXOS/job/FXOS_PRECOMMIT_BAZEL)
            
        Returns:
            Job information dict
        """
        url = f"{self.base_url.rstrip('/')}/{job_path.strip('/')}/api/json"
        
        try:
            r = self.session.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
            else:
                return {"error": f"HTTP {r.status_code}"}
        except requests.RequestException as e:
            return {"error": str(e)}
    
    def get_build_info(self, job_path: str, build_number: int) -> Dict[str, Any]:
        """
        Get information about a specific build.
        
        Args:
            job_path: Path to the job
            build_number: Build number
            
        Returns:
            Build information dict
        """
        url = f"{self.base_url.rstrip('/')}/{job_path.strip('/')}/{build_number}/api/json"
        
        try:
            r = self.session.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
            else:
                return {"error": f"HTTP {r.status_code}"}
        except requests.RequestException as e:
            return {"error": str(e)}
    
    def get_latest_build_number(self, job_path: str) -> Optional[int]:
        """
        Get the latest build number for a job.
        
        Args:
            job_path: Path to the job
            
        Returns:
            Build number or None
        """
        info = self.get_job_info(job_path)
        
        if "error" in info:
            return None
        
        last_build = info.get("lastBuild")
        if last_build:
            return last_build.get("number")
        
        return None
    
    def get_artifact(self, job_path: str, build_number: int, artifact_path: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Fetch an artifact from a build.
        
        Args:
            job_path: Path to the job
            build_number: Build number
            artifact_path: Path to artifact within the build
            
        Returns:
            Tuple of (content, error_message)
        """
        url = f"{self.base_url.rstrip('/')}/{job_path.strip('/')}/{build_number}/artifact/{artifact_path}"
        
        try:
            r = self.session.get(url, timeout=20)
            if r.status_code == 200:
                return r.text, None
            else:
                return None, f"HTTP {r.status_code}"
        except requests.RequestException as e:
            return None, str(e)
    
    def trigger_build(
        self,
        job_path: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Trigger a new build.
        
        Args:
            job_path: Path to the job
            parameters: Optional build parameters
            
        Returns:
            Dict with queue_id or error
        """
        if parameters:
            url = f"{self.base_url.rstrip('/')}/{job_path.strip('/')}/buildWithParameters"
        else:
            url = f"{self.base_url.rstrip('/')}/{job_path.strip('/')}/build"
        
        try:
            r = self.session.post(url, data=parameters or {}, timeout=30)
            
            if r.status_code in (200, 201):
                queue_location = r.headers.get("Location", "")
                queue_id = None
                if queue_location and "/queue/item/" in queue_location:
                    queue_id = queue_location.split("/queue/item/")[1].rstrip("/")
                
                return {
                    "success": True,
                    "queue_id": queue_id
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
    
    def get_queue_item(self, queue_id: str) -> Dict[str, Any]:
        """
        Get information about a queued build.
        
        Args:
            queue_id: Queue item ID
            
        Returns:
            Queue item information
        """
        url = f"{self.base_url.rstrip('/')}/queue/item/{queue_id}/api/json"
        
        try:
            r = self.session.get(url, timeout=10)
            if r.status_code == 200:
                return r.json()
            else:
                return {"error": f"HTTP {r.status_code}"}
        except requests.RequestException as e:
            return {"error": str(e)}
    
    def get_console_output(
        self,
        job_path: str,
        build_number: int,
        start: int = 0
    ) -> Tuple[str, int]:
        """
        Get console output for a build.
        
        Args:
            job_path: Path to the job
            build_number: Build number
            start: Byte offset to start from
            
        Returns:
            Tuple of (console_text, next_offset)
        """
        url = f"{self.base_url.rstrip('/')}/{job_path.strip('/')}/{build_number}/logText/progressiveText"
        
        try:
            r = self.session.get(url, params={"start": start}, timeout=30)
            if r.status_code == 200:
                next_offset = int(r.headers.get("X-Text-Size", start))
                return r.text, next_offset
            else:
                return "", start
        except requests.RequestException:
            return "", start
    
    def is_building(self, job_path: str, build_number: int) -> bool:
        """
        Check if a build is still running.
        
        Args:
            job_path: Path to the job
            build_number: Build number
            
        Returns:
            True if building, False otherwise
        """
        info = self.get_build_info(job_path, build_number)
        return info.get("building", False)
