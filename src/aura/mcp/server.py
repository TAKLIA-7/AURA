"""AURA Model Context Protocol (MCP) Server — Governed tool execution over MCP."""
from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from aura.sdk.interceptor import AuraGovernor


class AuraMCPServer:
    """
    Model Context Protocol (MCP) server exposing AURA tools to external agents
    (e.g., Claude Desktop, cursor, custom external LLMs) with mandatory governance.
    """

    def __init__(self, governor: Optional[AuraGovernor] = None) -> None:
        self.governor = governor or AuraGovernor()

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return all allowlisted tools in standard MCP format."""
        tools = []
        for tool_def in self.governor.registry.all_tools():
            tools.append({
                "name": tool_def.name,
                "description": tool_def.description,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "query": {"type": "string"},
                        "command": {"type": "string"},
                    },
                },
            })
        return tools

    async def handle_tool_call(
        self,
        name: str,
        arguments: Dict[str, Any],
        org_id: str = "default-org",
        role: str = "analyst",
        user_intent: str = "MCP external client request",
    ) -> Dict[str, Any]:
        """
        Executes an MCP tool call strictly governed by AURA.
        """
        result = await self.governor.execute_governed_action(
            tool_name=name,
            arguments=arguments,
            user_intent=user_intent,
            org_id=org_id,
            role=role,
        )
        if not result.success:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"AURA GOVERNANCE ERROR: {result.error}"}],
            }
        text_out = json.dumps(result.output) if isinstance(result.output, (dict, list)) else str(result.output)
        return {
            "isError": False,
            "content": [{"type": "text", "text": text_out}],
        }

    async def handle_json_rpc(self, request_json: str) -> str:
        """Handle incoming JSON-RPC 2.0 message."""
        try:
            req = json.loads(request_json)
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            if method == "tools/list":
                tools = self.list_tools()
                return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}})

            elif method == "tools/call":
                name = params.get("name")
                args = params.get("arguments", {})
                res = await self.handle_tool_call(name=name, arguments=args)
                return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": res})

            else:
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method '{method}' not found"},
                })
        except Exception as e:
            return json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)},
            })
