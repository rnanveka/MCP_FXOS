"""
Repackage Tool - Trigger repackage operations.

This tool triggers repackage operations for pipeline builds.
Repackaging re-runs the packaging step without rebuilding binaries.
"""

import os
import logging
from typing import Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)


class RepackageTool:
    """MCP Tool for triggering repackage operations."""
    
    description = "Trigger a repackage operation for a pipeline build"
    
    parameters = {
        "pipeline": {
            "type": "string",
            "description": "Pipeline to repackage: FXOS_PB or ASA"
        },
        "build_number": {
            "type": "integer",
            "description": "Build number to repackage"
        }
    }
    
    required_params = []  # Can be triggered without params for interactive mode
    
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
        pipeline: Optional[str] = None,
        build_number: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute the repackage tool.
        
        Args:
            pipeline: Pipeline to repackage (optional)
            build_number: Build number to repackage (optional)
            
        Returns:
            Dict with result and formatted output
        """
        # If no args, return instructions for interactive mode
        if not pipeline:
            return {
                "needs_input": True,
                "message": "Please specify pipeline and build number",
                "formatted_output": (
                    "🔄 **Repackage Operation**\n\n"
                    "Please provide:\n"
                    "• **Pipeline:** FXOS_PB or ASA\n"
                    "• **Build Number:** The build to repackage\n\n"
                    "Example: `/repackage FXOS_PB 11068`"
                )
            }
        
        pipeline = pipeline.upper()
        
        if pipeline not in ("FXOS_PB", "ASA"):
            return {
                "error": f"Unknown pipeline: {pipeline}",
                "formatted_output": f"❌ Unknown pipeline: {pipeline}\n\nAvailable: FXOS_PB, ASA"
            }
        
        if not build_number:
            return {
                "error": "Build number required",
                "formatted_output": "❌ Please specify a build number to repackage"
            }
        
        try:
            result = self._trigger_repackage(pipeline, build_number)
            
            if result.get("success"):
                return {
                    "success": True,
                    "pipeline": pipeline,
                    "build_number": build_number,
                    "formatted_output": (
                        f"✅ **Repackage triggered successfully!**\n\n"
                        f"• **Pipeline:** {pipeline}\n"
                        f"• **Build #:** {build_number}\n\n"
                        "The repackage operation has been queued."
                    )
                }
            else:
                error = result.get("error", "Unknown error")
                return {
                    "success": False,
                    "error": error,
                    "formatted_output": f"❌ Failed to trigger repackage: {error}"
                }
        
        except Exception as e:
            logger.exception(f"Error triggering repackage: {e}")
            return {
                "success": False,
                "error": str(e),
                "formatted_output": f"❌ Error triggering repackage: {e}"
            }
    
    def _trigger_repackage(self, pipeline: str, build_number: int) -> Dict[str, Any]:
        """
        Trigger a repackage operation.
        
        This is a placeholder - actual implementation depends on how
        repackaging is configured in Jenkins.
        
        Args:
            pipeline: Pipeline name
            build_number: Build to repackage
            
        Returns:
            Dict with success status
        """
        # Get job path for the pipeline
        if pipeline == "FXOS_PB":
            job_path = os.getenv("JENKINS_JOB_PATH_FXOS_PB", "")
        else:
            job_path = os.getenv("JENKINS_JOB_PATH_ASA", "")
        
        if not job_path:
            return {
                "success": False,
                "error": f"Job path not configured for {pipeline}"
            }
        
        # Option 1: Rebuild with REPACKAGE=true parameter
        repackage_url = f"{self.jenkins_base.rstrip('/')}/{job_path.strip('/')}/buildWithParameters"
        
        params = {
            "REPACKAGE": "true",
            "REPACKAGE_BUILD": str(build_number)
        }
        
        try:
            r = self.session.post(repackage_url, data=params, timeout=30)
            
            if r.status_code in (200, 201):
                return {"success": True}
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
