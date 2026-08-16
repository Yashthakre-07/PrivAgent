import os
import json
from typing import Dict, Any, List

class MCPToolRegistry:
    """
    Model Context Protocol (MCP) Tool Registry
    Exposes enterprise agent actions using standard MCP tool definitions and JSON-RPC compliance.
    """

    def __init__(self):
        self.tools = {
            "mcp_query_database": {
                "name": "mcp_query_database",
                "description": "Executes read-only SQL queries against enterprise relational database.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural language query or SQL string"}
                    },
                    "required": ["query"]
                }
            },
            "mcp_search_docs": {
                "name": "mcp_search_docs",
                "description": "Performs Hybrid Dense + Sparse BM25 RAG over enterprise documentation and PDFs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query for documentation RAG"}
                    },
                    "required": ["query"]
                }
            },
            "mcp_analyze_code": {
                "name": "mcp_analyze_code",
                "description": "Parses code AST, reviews git diffs, and greps repository source code.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Code search or AST parsing objective"}
                    },
                    "required": ["query"]
                }
            },
            "mcp_search_tickets": {
                "name": "mcp_search_tickets",
                "description": "Searches Jira tickets and enterprise incident tracking records.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Jira ticket search query"}
                    },
                    "required": ["query"]
                }
            },
            "mcp_web_search": {
                "name": "mcp_web_search",
                "description": "Fetches external web context via privacy-preserving search API.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Web search query"}
                    },
                    "required": ["query"]
                }
            }
        }

    def list_mcp_tools(self) -> List[Dict[str, Any]]:
        """Returns standard MCP JSON schemas for available tools."""
        return list(self.tools.values())

    def execute_mcp_tool(self, tool_name: str, arguments: Dict[str, Any], handler_fn) -> Dict[str, Any]:
        """Executes an MCP tool with audit logging and JSON-RPC response formatting."""
        if tool_name not in self.tools:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"MCP Tool '{tool_name}' not found in registry."},
                "id": 1
            }

        print(f"[MCP-Protocol] Executing tool '{tool_name}' with args: {arguments}")
        try:
            result = handler_fn(arguments)
            return {
                "jsonrpc": "2.0",
                "result": {
                    "tool": tool_name,
                    "status": "success",
                    "mcp_compliance": True,
                    "data": result
                },
                "id": 1
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32000, "message": str(e)},
                "id": 1
            }

mcp_registry = MCPToolRegistry()
