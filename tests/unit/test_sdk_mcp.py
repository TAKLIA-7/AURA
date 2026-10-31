"""Unit tests for AURA SDK Interceptor, LangChain Tool, and MCP Server."""
import json
import pytest
from pathlib import Path
from aura.sdk.interceptor import AuraGovernor, AuraLangChainTool
from aura.mcp.server import AuraMCPServer


@pytest.fixture
def test_governor(tmp_path: Path) -> AuraGovernor:
    return AuraGovernor(workspace_root=tmp_path, data_dir=tmp_path)


@pytest.mark.asyncio
async def test_sdk_fast_path(test_governor: AuraGovernor):
    # diagnostic.ping is fast-path allowed
    res = await test_governor.execute_governed_action(
        tool_name="diagnostic.ping",
        arguments={},
    )
    assert res.success is True
    assert "diagnostic ping successful" in res.output["message"]


@pytest.mark.asyncio
async def test_sdk_blocks_unauthorized_tool(test_governor: AuraGovernor):
    # Tool not in allowlist is immediately blocked
    res = await test_governor.execute_governed_action(
        tool_name="unauthorized.dangerous_tool",
        arguments={},
    )
    assert res.success is False
    assert "AURA GOVERNANCE BLOCK" in res.error


@pytest.mark.asyncio
async def test_sdk_path_traversal_blocked(test_governor: AuraGovernor):
    # Path traversal ../ is blocked
    res = await test_governor.execute_governed_action(
        tool_name="filesystem.read",
        arguments={"path": "../../../etc/passwd"},
    )
    assert res.success is False
    assert "Path traversal" in res.error


@pytest.mark.asyncio
async def test_mcp_server_protocol(test_governor: AuraGovernor):
    mcp = AuraMCPServer(governor=test_governor)

    # 1. tools/list
    list_req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    list_res_str = await mcp.handle_json_rpc(list_req)
    list_res = json.loads(list_res_str)
    assert "result" in list_res
    tool_names = [t["name"] for t in list_res["result"]["tools"]]
    assert "sqlite.query" in tool_names
    assert "diagnostic.ping" in tool_names

    # 2. tools/call diagnostic.ping
    call_req = json.dumps({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "diagnostic.ping", "arguments": {}},
    })
    call_res_str = await mcp.handle_json_rpc(call_req)
    call_res = json.loads(call_res_str)
    assert call_res["result"]["isError"] is False
    assert "diagnostic ping successful" in call_res["result"]["content"][0]["text"]
