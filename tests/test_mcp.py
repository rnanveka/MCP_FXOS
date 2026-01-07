"""
Tests for MCP Server functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import os


class TestMetricsTool:
    """Test the metrics tool."""
    
    def test_platforms_configuration(self):
        """Test that platform configurations are correct."""
        from mcp_server.tools.metrics import MetricsTool
        
        tool = MetricsTool()
        
        # Check FXOS platforms
        assert len(tool.FXOS_PLATFORMS) == 9
        platform_ids = [p["id"] for p in tool.FXOS_PLATFORMS]
        assert "arm" in platform_ids
        assert "fp4k" in platform_ids
        
        # Check ASA platforms
        assert len(tool.ASA_PLATFORMS) == 4
        platform_ids = [p["id"] for p in tool.ASA_PLATFORMS]
        assert "arm" in platform_ids
        assert "arm8" in platform_ids
    
    def test_format_duration(self):
        """Test duration formatting."""
        from mcp_server.tools.metrics import MetricsTool
        
        tool = MetricsTool()
        
        assert tool._format_duration(65) == "01:05"
        assert tool._format_duration(3661) == "61:01"
        assert tool._format_duration(0) == "00:00"
    
    def test_build_regex_patterns(self):
        """Test build time regex patterns."""
        from mcp_server.tools.metrics import MetricsTool
        
        tool = MetricsTool()
        
        test_text = """
        Some log output
        BUILD_TIME_START: Tue Nov 25 05:21:30 UTC 2025
        Building...
        BUILD_TIME_END: Tue Nov 25 05:45:30 UTC 2025
        Done
        """
        
        start, end = tool._parse_build_times(test_text)
        
        assert start == "Tue Nov 25 05:21:30 UTC 2025"
        assert end == "Tue Nov 25 05:45:30 UTC 2025"
    
    @patch.dict(os.environ, {
        "JENKINS_BASE_URL": "https://jenkins.example.com",
        "JENKINS_USER": "testuser",
        "JENKINS_API_TOKEN": "testtoken"
    })
    def test_tool_initialization(self):
        """Test tool initializes with env vars."""
        from mcp_server.tools.metrics import MetricsTool
        
        tool = MetricsTool()
        
        assert tool.jenkins_base == "https://jenkins.example.com"
        assert tool.jenkins_user == "testuser"


class TestQueryTool:
    """Test the query tool."""
    
    def test_branch_configurations(self):
        """Test branch configurations."""
        from mcp_server.tools.query import QueryTool
        
        tool = QueryTool()
        
        assert "fxos_19" in tool.BRANCHES
        assert "cairo" in tool.BRANCHES
        assert "lina" in tool.BRANCHES
        
        # Check cairo is an alias for lina
        cairo_config = tool.BRANCHES["cairo"]
        assert cairo_config["splunk_filter"] == 'branch="cairo"'
    
    def test_format_branch_status_success(self):
        """Test formatting successful branch status."""
        from mcp_server.tools.query import QueryTool
        
        tool = QueryTool()
        
        result = {
            "display_name": "FXOS 2.19",
            "status": "✅ SUCCESS",
            "make_status": "SUCCESS",
            "bazel_status": "SUCCESS",
            "review": "12345",
            "review_url": "https://swarm.example.com/reviews/12345",
            "error": None
        }
        
        formatted = tool._format_branch_status(result)
        
        assert "FXOS 2.19" in formatted
        assert "SUCCESS" in formatted
        assert "12345" in formatted
    
    def test_format_branch_status_failure(self):
        """Test formatting failed branch status."""
        from mcp_server.tools.query import QueryTool
        
        tool = QueryTool()
        
        result = {
            "display_name": "Cairo",
            "status": "❌ PLATFORM FAILURE",
            "make_status": "FAILURE",
            "bazel_status": "SUCCESS",
            "review": "12345",
            "review_url": "",
            "error": "Build failed: missing dependency"
        }
        
        formatted = tool._format_branch_status(result)
        
        assert "Cairo" in formatted
        assert "PLATFORM FAILURE" in formatted
        assert "missing dependency" in formatted


class TestBuildsTool:
    """Test the builds tool."""
    
    def test_pipeline_configurations(self):
        """Test pipeline configurations."""
        from mcp_server.tools.builds import BuildsTool
        
        tool = BuildsTool()
        
        assert "FXOS_PB" in tool.PIPELINES
        assert "ASA" in tool.PIPELINES
        
        fxos_config = tool.PIPELINES["FXOS_PB"]
        assert fxos_config["job_path_env"] == "JENKINS_JOB_PATH_FXOS_PB"
    
    def test_invalid_pipeline(self):
        """Test handling of invalid pipeline."""
        from mcp_server.tools.builds import BuildsTool
        
        tool = BuildsTool()
        
        result = tool.execute("INVALID_PIPELINE", "main")
        
        assert "error" in result
        assert "Unknown pipeline" in result["error"]


class TestMCPServer:
    """Test the MCP server."""
    
    @patch('mcp_server.server.metrics_tool')
    @patch('mcp_server.server.query_tool')
    @patch('mcp_server.server.builds_tool')
    @patch('mcp_server.server.repackage_tool')
    def test_health_endpoint(self, mock_repack, mock_builds, mock_query, mock_metrics):
        """Test health check endpoint."""
        from mcp_server.server import app
        
        client = app.test_client()
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "healthy"
        assert "tools" in data
    
    @patch('mcp_server.server.metrics_tool')
    @patch('mcp_server.server.query_tool')
    @patch('mcp_server.server.builds_tool')
    @patch('mcp_server.server.repackage_tool')
    def test_list_tools_endpoint(self, mock_repack, mock_builds, mock_query, mock_metrics):
        """Test tools listing endpoint."""
        # Setup mocks
        mock_metrics.description = "Get metrics"
        mock_metrics.parameters = {}
        mock_query.description = "Query branch"
        mock_query.parameters = {}
        mock_builds.description = "Start build"
        mock_builds.parameters = {}
        mock_repack.description = "Repackage"
        mock_repack.parameters = {}
        
        from mcp_server.server import app
        
        client = app.test_client()
        response = client.get("/tools")
        
        assert response.status_code == 200
        data = response.get_json()
        assert "tools" in data


class TestJenkinsClient:
    """Test the Jenkins client."""
    
    @patch.dict(os.environ, {
        "JENKINS_BASE_URL": "https://jenkins.example.com",
        "JENKINS_USER": "testuser",
        "JENKINS_API_TOKEN": "testtoken"
    })
    def test_client_initialization(self):
        """Test client initializes with env vars."""
        from mcp_server.clients.jenkins_client import JenkinsClient
        
        client = JenkinsClient()
        
        assert client.base_url == "https://jenkins.example.com"
        assert client.user == "testuser"
    
    def test_session_creation(self):
        """Test session is created with auth."""
        from mcp_server.clients.jenkins_client import JenkinsClient
        
        client = JenkinsClient(
            base_url="https://jenkins.example.com",
            user="testuser",
            token="testtoken"
        )
        
        session = client.session
        
        assert session.auth == ("testuser", "testtoken")
        assert "Accept" in session.headers


class TestSplunkClient:
    """Test the Splunk client."""
    
    @patch.dict(os.environ, {
        "SPLUNK_HOST": "https://splunk.example.com:8089",
        "SPLUNK_TOKEN": "testtoken"
    })
    def test_client_initialization(self):
        """Test client initializes with env vars."""
        from mcp_server.clients.splunk_client import SplunkClient
        
        client = SplunkClient()
        
        assert client.host == "https://splunk.example.com:8089"
        assert client.token == "testtoken"
    
    def test_safe_float(self):
        """Test safe float conversion."""
        from mcp_server.clients.splunk_client import SplunkClient
        
        assert SplunkClient._safe_float("123.45") == 123.45
        assert SplunkClient._safe_float(None) is None
        assert SplunkClient._safe_float("invalid") is None
    
    def test_safe_int(self):
        """Test safe int conversion."""
        from mcp_server.clients.splunk_client import SplunkClient
        
        assert SplunkClient._safe_int("123") == 123
        assert SplunkClient._safe_int(None) == 0
        assert SplunkClient._safe_int("invalid") == 0
