"""MCP Clients package - clients for external MCP servers."""

from mcp_server.clients.jenkins_client import JenkinsClient
from mcp_server.clients.splunk_client import SplunkClient

__all__ = ["JenkinsClient", "SplunkClient"]
