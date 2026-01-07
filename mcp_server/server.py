"""
MCP Server - Main orchestrator for Pipeline Notify.

This server exposes MCP tools that can be called by:
- The Webex bot (via HTTP API)
- MCP clients (via MCP protocol)
- Other automation systems

Tools:
- get_metrics: Get Jenkins build metrics
- query_branch: Query Splunk for branch status
- start_build: Trigger a Jenkins build
- list_failures: List all failing branches
- repackage: Trigger repackage operation
"""

import os
import logging
import asyncio
from typing import Any, Dict, Optional
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from mcp_server.tools.metrics import MetricsTool
from mcp_server.tools.query import QueryTool
from mcp_server.tools.builds import BuildsTool
from mcp_server.tools.repackage import RepackageTool

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize tools
metrics_tool = MetricsTool()
query_tool = QueryTool()
builds_tool = BuildsTool()
repackage_tool = RepackageTool()

# Tool registry
TOOLS = {
    "get_metrics": metrics_tool,
    "query_branch": query_tool,
    "start_build": builds_tool,
    "list_failures": query_tool,  # Uses same tool with different method
    "repackage": repackage_tool,
}


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "pipeline-notify-mcp",
        "tools": list(TOOLS.keys())
    })


@app.route("/tools", methods=["GET"])
def list_tools():
    """List available MCP tools."""
    tools_info = []
    for name, tool in TOOLS.items():
        tools_info.append({
            "name": name,
            "description": tool.description,
            "parameters": tool.parameters
        })
    return jsonify({"tools": tools_info})


@app.route("/tools/execute", methods=["POST"])
def execute_tool():
    """
    Execute an MCP tool.
    
    Request body:
    {
        "tool": "tool_name",
        "args": {...}
    }
    
    Returns:
        Tool execution result
    """
    data = request.json or {}
    tool_name = data.get("tool")
    args = data.get("args", {})
    
    logger.info(f"Executing tool: {tool_name} with args: {args}")
    
    if not tool_name:
        return jsonify({"error": "tool name required"}), 400
    
    if tool_name not in TOOLS:
        return jsonify({
            "error": f"Unknown tool: {tool_name}",
            "available_tools": list(TOOLS.keys())
        }), 404
    
    try:
        tool = TOOLS[tool_name]
        
        # Handle special case for list_failures
        if tool_name == "list_failures":
            result = tool.list_failures(**args)
        else:
            result = tool.execute(**args)
        
        return jsonify(result)
    
    except Exception as e:
        logger.exception(f"Error executing tool {tool_name}: {e}")
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
# MCP Protocol Support (for direct MCP clients)
# ─────────────────────────────────────────────

class MCPServer:
    """
    MCP Protocol server for direct MCP client connections.
    
    This class implements the MCP protocol for tools, allowing
    MCP clients to discover and invoke tools directly.
    """
    
    def __init__(self):
        self.tools = TOOLS
    
    async def handle_list_tools(self) -> Dict[str, Any]:
        """Handle MCP list_tools request."""
        tools_list = []
        for name, tool in self.tools.items():
            tools_list.append({
                "name": name,
                "description": tool.description,
                "inputSchema": {
                    "type": "object",
                    "properties": tool.parameters,
                    "required": tool.required_params
                }
            })
        return {"tools": tools_list}
    
    async def handle_call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP call_tool request."""
        if name not in self.tools:
            raise ValueError(f"Unknown tool: {name}")
        
        tool = self.tools[name]
        
        # Handle special case for list_failures
        if name == "list_failures":
            result = tool.list_failures(**arguments)
        else:
            result = tool.execute(**arguments)
        
        return {"content": [{"type": "text", "text": result.get("formatted_output", str(result))}]}


def run_http_server():
    """Run the HTTP server for bot/API access."""
    port = int(os.getenv("MCP_SERVER_PORT", 8080))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    logger.info(f"Starting MCP HTTP Server on port {port}")
    logger.info(f"Available tools: {list(TOOLS.keys())}")
    
    app.run(host="0.0.0.0", port=port, debug=debug)


def main():
    """Main entry point."""
    run_http_server()


if __name__ == "__main__":
    main()
