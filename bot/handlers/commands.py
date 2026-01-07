"""
Command Handler - Process Webex message commands.

Supported commands:
- /metrics [FXOS|ASA] [build_number] - Get Jenkins build metrics
- /query [branch] - Query Splunk for branch status
- /build - Trigger a build (shows pipeline dropdown)
- /repackage - Trigger repackage operation
- /help - Show available commands
- Natural language queries (e.g., "Is Cairo passing?")
"""

import re
import os
import logging
from typing import Optional, Dict, Any
from webexteamssdk import WebexTeamsAPI

import requests

logger = logging.getLogger(__name__)


class CommandHandler:
    """Handles text commands from Webex messages."""
    
    # Command patterns
    METRICS_PATTERN = re.compile(
        r"^/metrics\s+(fxos|asa)(?:\s+(\d+))?$",
        re.IGNORECASE
    )
    QUERY_PATTERN = re.compile(
        r"^/query\s+(\w+)$",
        re.IGNORECASE
    )
    BUILD_PATTERN = re.compile(r"^/build$", re.IGNORECASE)
    REPACKAGE_PATTERN = re.compile(r"^/repackage$", re.IGNORECASE)
    HELP_PATTERN = re.compile(r"^/help$", re.IGNORECASE)
    
    # Natural language patterns
    NL_STATUS_PATTERN = re.compile(
        r"(?:is|how is|what'?s?)\s+(\w+)\s+(?:passing|doing|status|failing)",
        re.IGNORECASE
    )
    NL_METRICS_PATTERN = re.compile(
        r"(?:get|show|display)\s+metrics?\s+(?:for\s+)?(\w+)",
        re.IGNORECASE
    )
    
    def __init__(self, webex_api: WebexTeamsAPI):
        """
        Initialize command handler.
        
        Args:
            webex_api: Webex Teams API client
        """
        self.webex = webex_api
        self.mcp_server_url = os.getenv("MCP_SERVER_URL", "http://localhost:8080")
    
    def handle_message(self, message) -> Dict[str, Any]:
        """
        Process an incoming message and execute the appropriate command.
        
        Args:
            message: Webex message object
            
        Returns:
            Dict with response details
        """
        text = message.text.strip() if message.text else ""
        room_id = message.roomId
        person_email = message.personEmail
        
        logger.info(f"Processing message from {person_email}: {text[:50]}...")
        
        # Try to match commands
        response_text = None
        
        # /metrics command
        match = self.METRICS_PATTERN.match(text)
        if match:
            job_type = match.group(1).upper()
            build_number = int(match.group(2)) if match.group(2) else None
            response_text = self._handle_metrics(job_type, build_number)
        
        # /query command
        if not response_text:
            match = self.QUERY_PATTERN.match(text)
            if match:
                branch = match.group(1)
                response_text = self._handle_query(branch)
        
        # /build command
        if not response_text and self.BUILD_PATTERN.match(text):
            return self._send_build_card(room_id)
        
        # /repackage command
        if not response_text and self.REPACKAGE_PATTERN.match(text):
            response_text = self._handle_repackage()
        
        # /help command
        if not response_text and self.HELP_PATTERN.match(text):
            response_text = self._get_help_text()
        
        # Natural language: "Is Cairo passing?"
        if not response_text:
            match = self.NL_STATUS_PATTERN.search(text)
            if match:
                branch = match.group(1)
                response_text = self._handle_query(branch)
        
        # Natural language: "Get metrics for FXOS"
        if not response_text:
            match = self.NL_METRICS_PATTERN.search(text)
            if match:
                job_type = match.group(1).upper()
                if job_type in ("FXOS", "ASA"):
                    response_text = self._handle_metrics(job_type)
        
        # Default: unknown command
        if not response_text:
            response_text = (
                "I didn't understand that command. "
                "Type `/help` to see available commands."
            )
        
        # Send response
        self._send_message(room_id, response_text)
        
        return {"status": "sent", "room_id": room_id}
    
    def _handle_metrics(self, job_type: str, build_number: Optional[int] = None) -> str:
        """
        Get Jenkins build metrics.
        
        Args:
            job_type: FXOS or ASA
            build_number: Optional specific build number
            
        Returns:
            Formatted metrics response
        """
        try:
            payload = {
                "tool": "get_metrics",
                "args": {
                    "job_type": job_type,
                    "build_number": build_number
                }
            }
            
            response = requests.post(
                f"{self.mcp_server_url}/tools/execute",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("formatted_output", "No metrics available")
            else:
                return f"❌ Error fetching metrics: HTTP {response.status_code}"
        
        except requests.RequestException as e:
            logger.error(f"Error calling MCP server: {e}")
            return f"❌ Error connecting to MCP server: {e}"
    
    def _handle_query(self, branch: str) -> str:
        """
        Query Splunk for branch status.
        
        Args:
            branch: Branch name (e.g., cairo, fxos_19)
            
        Returns:
            Formatted branch status
        """
        try:
            payload = {
                "tool": "query_branch",
                "args": {
                    "branch": branch.lower()
                }
            }
            
            response = requests.post(
                f"{self.mcp_server_url}/tools/execute",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("formatted_output", "No data available")
            else:
                return f"❌ Error querying branch: HTTP {response.status_code}"
        
        except requests.RequestException as e:
            logger.error(f"Error calling MCP server: {e}")
            return f"❌ Error connecting to MCP server: {e}"
    
    def _handle_repackage(self) -> str:
        """Trigger repackage operation."""
        try:
            payload = {
                "tool": "repackage",
                "args": {}
            }
            
            response = requests.post(
                f"{self.mcp_server_url}/tools/execute",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                return "✅ Repackage operation triggered successfully"
            else:
                return f"❌ Error triggering repackage: HTTP {response.status_code}"
        
        except requests.RequestException as e:
            logger.error(f"Error calling MCP server: {e}")
            return f"❌ Error connecting to MCP server: {e}"
    
    def _send_build_card(self, room_id: str) -> Dict[str, Any]:
        """
        Send a build selection card with dropdowns.
        
        Args:
            room_id: Webex room ID
            
        Returns:
            Response details
        """
        from bot.handlers.cards import CardHandler
        
        card = CardHandler.create_pipeline_selection_card()
        
        self.webex.messages.create(
            roomId=room_id,
            text="Select a pipeline to build",  # Fallback text
            attachments=[{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card
            }]
        )
        
        return {"status": "card_sent", "room_id": room_id, "card": "pipeline_selection"}
    
    def _get_help_text(self) -> str:
        """Get help text with available commands."""
        return """
**🔧 Pipeline Notify Bot - Available Commands**

**Commands:**
• `/metrics FXOS [build_number]` - Get FXOS build metrics
• `/metrics ASA [build_number]` - Get ASA build metrics
• `/query <branch>` - Query branch status (cairo, fxos_19, fxos_18)
• `/build` - Start a new build (with dropdown selection)
• `/repackage` - Trigger repackage operation
• `/help` - Show this help message

**Natural Language:**
• "Is Cairo passing?" - Check branch status
• "Get metrics for FXOS" - Show build metrics

**Examples:**
• `/metrics FXOS 11068` - Metrics for specific build
• `/query cairo` - Check Cairo branch status
"""
    
    def _send_message(self, room_id: str, text: str) -> None:
        """Send a markdown message to a room."""
        try:
            self.webex.messages.create(
                roomId=room_id,
                markdown=text
            )
        except Exception as e:
            logger.error(f"Error sending message: {e}")
