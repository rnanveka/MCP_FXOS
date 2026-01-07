"""
Card Handler - Build and process Webex Adaptive Cards.

Handles:
- Pipeline selection dropdown
- Branch selection dropdown
- Build confirmation
- Card action submissions
"""

import os
import logging
from typing import Dict, Any, List, Optional
from webexteamssdk import WebexTeamsAPI

import requests

logger = logging.getLogger(__name__)


class CardHandler:
    """Handles Webex Adaptive Card creation and action processing."""
    
    # Available pipelines
    PIPELINES = [
        {"title": "FXOS Precommit Bazel", "value": "FXOS_PB"},
        {"title": "ASA Precommit Bazel", "value": "ASA"},
    ]
    
    # Available branches per pipeline
    BRANCHES = {
        "FXOS_PB": [
            {"title": "Main", "value": "main"},
            {"title": "FXOS 2.19", "value": "fxos_2_19"},
            {"title": "FXOS 2.18", "value": "fxos_2_18"},
        ],
        "ASA": [
            {"title": "Main", "value": "main"},
            {"title": "Cairo", "value": "cairo"},
        ],
    }
    
    def __init__(self, webex_api: WebexTeamsAPI):
        """
        Initialize card handler.
        
        Args:
            webex_api: Webex Teams API client
        """
        self.webex = webex_api
        self.mcp_server_url = os.getenv("MCP_SERVER_URL", "http://localhost:8080")
    
    def handle_action(self, action) -> Dict[str, Any]:
        """
        Process a card action (form submission).
        
        Args:
            action: Webex attachment action object
            
        Returns:
            Dict with response details
        """
        inputs = action.inputs or {}
        action_type = inputs.get("action_type", "")
        room_id = action.roomId
        person_email = action.personEmail
        
        logger.info(f"Processing card action from {person_email}: {action_type}")
        
        if action_type == "select_pipeline":
            return self._handle_pipeline_selection(room_id, inputs)
        elif action_type == "select_branch":
            return self._handle_branch_selection(room_id, inputs)
        elif action_type == "confirm_build":
            return self._handle_build_confirmation(room_id, inputs)
        elif action_type == "cancel":
            self._send_message(room_id, "❌ Build cancelled.")
            return {"status": "cancelled"}
        else:
            self._send_message(room_id, "Unknown card action.")
            return {"status": "unknown_action", "action_type": action_type}
    
    def _handle_pipeline_selection(self, room_id: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle pipeline selection and show branch dropdown.
        
        Args:
            room_id: Webex room ID
            inputs: Card input values
            
        Returns:
            Response details
        """
        pipeline = inputs.get("pipeline")
        
        if not pipeline:
            self._send_message(room_id, "Please select a pipeline.")
            return {"status": "error", "message": "No pipeline selected"}
        
        # Send branch selection card
        card = self.create_branch_selection_card(pipeline)
        
        self.webex.messages.create(
            roomId=room_id,
            text=f"Select a branch for {pipeline}",
            attachments=[{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card
            }]
        )
        
        return {"status": "branch_card_sent", "pipeline": pipeline}
    
    def _handle_branch_selection(self, room_id: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle branch selection and show confirmation.
        
        Args:
            room_id: Webex room ID
            inputs: Card input values
            
        Returns:
            Response details
        """
        pipeline = inputs.get("pipeline")
        branch = inputs.get("branch")
        
        if not pipeline or not branch:
            self._send_message(room_id, "Please select both pipeline and branch.")
            return {"status": "error", "message": "Missing selection"}
        
        # Send confirmation card
        card = self.create_build_confirmation_card(pipeline, branch)
        
        self.webex.messages.create(
            roomId=room_id,
            text=f"Confirm build: {pipeline} on {branch}",
            attachments=[{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card
            }]
        )
        
        return {"status": "confirmation_card_sent", "pipeline": pipeline, "branch": branch}
    
    def _handle_build_confirmation(self, room_id: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle build confirmation and trigger the build.
        
        Args:
            room_id: Webex room ID
            inputs: Card input values
            
        Returns:
            Response details
        """
        pipeline = inputs.get("pipeline")
        branch = inputs.get("branch")
        
        if not pipeline or not branch:
            self._send_message(room_id, "❌ Missing pipeline or branch information.")
            return {"status": "error", "message": "Missing information"}
        
        # Call MCP server to trigger build
        try:
            payload = {
                "tool": "start_build",
                "args": {
                    "pipeline": pipeline,
                    "branch": branch
                }
            }
            
            response = requests.post(
                f"{self.mcp_server_url}/tools/execute",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                build_number = data.get("build_number", "N/A")
                self._send_message(
                    room_id,
                    f"✅ **Build triggered successfully!**\n\n"
                    f"• **Pipeline:** {pipeline}\n"
                    f"• **Branch:** {branch}\n"
                    f"• **Build #:** {build_number}"
                )
                return {"status": "build_triggered", "build_number": build_number}
            else:
                self._send_message(room_id, f"❌ Error triggering build: HTTP {response.status_code}")
                return {"status": "error", "http_status": response.status_code}
        
        except requests.RequestException as e:
            logger.error(f"Error calling MCP server: {e}")
            self._send_message(room_id, f"❌ Error connecting to MCP server: {e}")
            return {"status": "error", "exception": str(e)}
    
    @staticmethod
    def create_pipeline_selection_card() -> Dict[str, Any]:
        """
        Create a pipeline selection card.
        
        Returns:
            Adaptive Card JSON
        """
        return {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.3",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "🚀 Start a Build",
                    "size": "Large",
                    "weight": "Bolder"
                },
                {
                    "type": "TextBlock",
                    "text": "Select the pipeline you want to build:",
                    "wrap": True
                },
                {
                    "type": "Input.ChoiceSet",
                    "id": "pipeline",
                    "style": "compact",
                    "isRequired": True,
                    "choices": [
                        {"title": p["title"], "value": p["value"]}
                        for p in CardHandler.PIPELINES
                    ]
                }
            ],
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "Next",
                    "data": {"action_type": "select_pipeline"}
                },
                {
                    "type": "Action.Submit",
                    "title": "Cancel",
                    "data": {"action_type": "cancel"}
                }
            ]
        }
    
    @staticmethod
    def create_branch_selection_card(pipeline: str) -> Dict[str, Any]:
        """
        Create a branch selection card for a pipeline.
        
        Args:
            pipeline: Selected pipeline name
            
        Returns:
            Adaptive Card JSON
        """
        branches = CardHandler.BRANCHES.get(pipeline, [])
        
        return {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.3",
            "body": [
                {
                    "type": "TextBlock",
                    "text": f"🌿 Select Branch for {pipeline}",
                    "size": "Large",
                    "weight": "Bolder"
                },
                {
                    "type": "Input.ChoiceSet",
                    "id": "branch",
                    "style": "compact",
                    "isRequired": True,
                    "choices": [
                        {"title": b["title"], "value": b["value"]}
                        for b in branches
                    ]
                }
            ],
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "Next",
                    "data": {
                        "action_type": "select_branch",
                        "pipeline": pipeline
                    }
                },
                {
                    "type": "Action.Submit",
                    "title": "Cancel",
                    "data": {"action_type": "cancel"}
                }
            ]
        }
    
    @staticmethod
    def create_build_confirmation_card(pipeline: str, branch: str) -> Dict[str, Any]:
        """
        Create a build confirmation card.
        
        Args:
            pipeline: Selected pipeline
            branch: Selected branch
            
        Returns:
            Adaptive Card JSON
        """
        return {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.3",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "⚠️ Confirm Build",
                    "size": "Large",
                    "weight": "Bolder"
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "Pipeline:", "value": pipeline},
                        {"title": "Branch:", "value": branch}
                    ]
                },
                {
                    "type": "TextBlock",
                    "text": "Are you sure you want to start this build?",
                    "wrap": True
                }
            ],
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "✅ Confirm",
                    "style": "positive",
                    "data": {
                        "action_type": "confirm_build",
                        "pipeline": pipeline,
                        "branch": branch
                    }
                },
                {
                    "type": "Action.Submit",
                    "title": "❌ Cancel",
                    "style": "destructive",
                    "data": {"action_type": "cancel"}
                }
            ]
        }
    
    def _send_message(self, room_id: str, text: str) -> None:
        """Send a markdown message to a room."""
        try:
            self.webex.messages.create(
                roomId=room_id,
                markdown=text
            )
        except Exception as e:
            logger.error(f"Error sending message: {e}")
