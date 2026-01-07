"""
Tests for Webex Bot functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestCommandHandler:
    """Test the command handler."""
    
    def test_metrics_pattern_fxos(self):
        """Test FXOS metrics command pattern."""
        from bot.handlers.commands import CommandHandler
        
        pattern = CommandHandler.METRICS_PATTERN
        
        # Valid commands
        match = pattern.match("/metrics FXOS")
        assert match is not None
        assert match.group(1).upper() == "FXOS"
        assert match.group(2) is None
        
        match = pattern.match("/metrics fxos 11068")
        assert match is not None
        assert match.group(1).lower() == "fxos"
        assert match.group(2) == "11068"
    
    def test_metrics_pattern_asa(self):
        """Test ASA metrics command pattern."""
        from bot.handlers.commands import CommandHandler
        
        pattern = CommandHandler.METRICS_PATTERN
        
        match = pattern.match("/metrics ASA 5432")
        assert match is not None
        assert match.group(1).upper() == "ASA"
        assert match.group(2) == "5432"
    
    def test_query_pattern(self):
        """Test query command pattern."""
        from bot.handlers.commands import CommandHandler
        
        pattern = CommandHandler.QUERY_PATTERN
        
        match = pattern.match("/query cairo")
        assert match is not None
        assert match.group(1) == "cairo"
        
        match = pattern.match("/query fxos_19")
        assert match is not None
        assert match.group(1) == "fxos_19"
    
    def test_natural_language_status(self):
        """Test natural language status pattern."""
        from bot.handlers.commands import CommandHandler
        
        pattern = CommandHandler.NL_STATUS_PATTERN
        
        match = pattern.search("Is Cairo passing?")
        assert match is not None
        assert match.group(1).lower() == "cairo"
        
        match = pattern.search("How is fxos_19 doing?")
        assert match is not None
        assert match.group(1) == "fxos_19"
    
    def test_help_pattern(self):
        """Test help command pattern."""
        from bot.handlers.commands import CommandHandler
        
        pattern = CommandHandler.HELP_PATTERN
        
        assert pattern.match("/help") is not None
        assert pattern.match("/Help") is not None
        assert pattern.match("/HELP") is not None
    
    @patch('bot.handlers.commands.requests')
    def test_handle_metrics_success(self, mock_requests):
        """Test successful metrics handling."""
        from bot.handlers.commands import CommandHandler
        
        # Mock Webex API
        mock_webex = Mock()
        handler = CommandHandler(mock_webex)
        
        # Mock MCP server response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "formatted_output": "🔧 **Jenkins Build Metrics**\n..."
        }
        mock_requests.post.return_value = mock_response
        
        result = handler._handle_metrics("FXOS", 11068)
        
        assert "Jenkins Build Metrics" in result


class TestCardHandler:
    """Test the card handler."""
    
    def test_create_pipeline_selection_card(self):
        """Test pipeline selection card creation."""
        from bot.handlers.cards import CardHandler
        
        card = CardHandler.create_pipeline_selection_card()
        
        assert card["type"] == "AdaptiveCard"
        assert card["version"] == "1.3"
        assert len(card["body"]) > 0
        assert len(card["actions"]) == 2
    
    def test_create_branch_selection_card(self):
        """Test branch selection card creation."""
        from bot.handlers.cards import CardHandler
        
        card = CardHandler.create_branch_selection_card("FXOS_PB")
        
        assert card["type"] == "AdaptiveCard"
        assert "FXOS_PB" in str(card)
    
    def test_create_build_confirmation_card(self):
        """Test build confirmation card creation."""
        from bot.handlers.cards import CardHandler
        
        card = CardHandler.create_build_confirmation_card("FXOS_PB", "main")
        
        assert card["type"] == "AdaptiveCard"
        assert "Confirm Build" in str(card)
        
        # Check facts
        facts = None
        for body_item in card["body"]:
            if body_item.get("type") == "FactSet":
                facts = body_item["facts"]
                break
        
        assert facts is not None
        assert len(facts) == 2


class TestWebhookApp:
    """Test the Flask webhook app."""
    
    @patch('bot.app.webex_api')
    @patch('bot.app.command_handler')
    def test_health_check(self, mock_cmd_handler, mock_webex):
        """Test health check endpoint."""
        from bot.app import app
        
        client = app.test_client()
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "healthy"
        assert data["service"] == "pipeline-notify-bot"
