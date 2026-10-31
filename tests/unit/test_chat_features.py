"""Unit tests for AURA Chat screen features and extensions."""
import pytest
pytest.importorskip("textual")
from pathlib import Path
from aura.ui.screens.chat import ChatMessage, ChatView
from aura.config import AURAConfig, DisplayConfig


def test_chat_message_rendering():
    # User message
    msg_user = ChatMessage(role="user", content="Hello AURA", metadata={"attached_files": ["pyproject.toml"]})
    rendered = msg_user.render()
    assert "YOU" in rendered.plain
    assert "Hello AURA" in rendered.plain
    assert "[@pyproject.toml]" in rendered.plain

    # Agent message
    msg_agent = ChatMessage(role="agent", content="Ready to assist.")
    rendered = msg_agent.render()
    assert "AURA AGENT" in rendered.plain
    assert "Ready to assist." in rendered.plain

    # Tool proposed
    msg_prop = ChatMessage(role="tool_proposed", metadata={"tool": "filesystem.list", "args": {"path": "."}})
    rendered = msg_prop.render()
    assert "Listed directory" in rendered.plain or "filesystem.list" in rendered.plain

    # Action blocked
    msg_blk = ChatMessage(role="action_blocked", metadata={"tool": "shell.execute", "reason": "Destructive command"})
    rendered = msg_blk.render()
    assert "BLOCKED" in rendered.plain
    assert "Destructive command" in rendered.plain

    # Action executed
    msg_exec = ChatMessage(role="action_executed", metadata={"tool": "sqlite.query", "success": True, "output": {"stdout": "success"}})
    rendered = msg_exec.render()
    assert "✓" in rendered.plain

    # Shell shortcut
    msg_sh = ChatMessage(role="shell_shortcut", metadata={"command": "whoami", "stdout": "testuser"})
    rendered = msg_sh.render()
    assert "!whoami" in rendered.plain
    assert "testuser" in rendered.plain


def test_expand_file_refs(tmp_path):
    test_file = tmp_path / "sample.txt"
    test_file.write_text("sample file content", encoding="utf-8")

    chat_view = ChatView()
    # Test valid file
    res, attached = chat_view._expand_file_refs(f"Check @{test_file.name}", base_dir=tmp_path)
    assert attached == [test_file.name]
    assert "sample file content" in res

    # Test nonexistent file
    res_none, attached_none = chat_view._expand_file_refs("Check @nonexistent.txt", base_dir=tmp_path)
    assert attached_none == []
    assert "@nonexistent.txt" in res_none


def test_clear_and_compact_shortcuts():
    chat_view = ChatView()
    chat_view.message_history.append(ChatMessage(role="user", content="Msg 1"))
    chat_view.message_history.append(ChatMessage(role="agent", content="Msg 2"))
    assert len(chat_view.message_history) == 2

    chat_view.clear_history()
    assert len(chat_view.message_history) == 0

    # Test compact summary
    summary = chat_view.compact_history()
    assert "compact" in summary.lower() or "summary" in summary.lower()
