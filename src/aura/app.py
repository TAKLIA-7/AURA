"""AURA main Textual application."""
from __future__ import annotations
import asyncio
from typing import Optional

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Label, Static, TabbedContent, TabPane
from textual.containers import Container, Horizontal
from textual.binding import Binding
from rich.text import Text

from aura.config import get_config
from aura.agent import AURAOrchestrator
from aura.observability import get_metrics
from aura.ui.theme import AURA_CSS
from aura.ui.screens import (
    ChatView, RunsView, LogsView, MonitorView, PoliciesView, SettingsView,
)


class AURAHeader(Static):
    """AURA top header with live status indicators and telemetry summary."""

    DEFAULT_CSS = """
    AURAHeader {
        height: 3;
        background: #0b0b1c;
        border-bottom: solid #1e1e3a;
        padding: 0 2;
        layout: horizontal;
    }
    """

    def render(self) -> Text:
        m = get_metrics()
        cfg = get_config()

        agent_dot = "●" if m.agent_connected else "○"
        agent_color = "bright_green" if m.agent_connected else "bright_red"
        jev_dot = "●" if m.jev_connected else "○"
        jev_color = "bright_green" if m.jev_connected else ("yellow" if cfg.jev.mock_mode else "bright_red")
        jev_label = "MOCK" if cfg.jev.mock_mode else (cfg.jev.provider.upper() if cfg.jev.provider else "LIVE")

        t = Text()
        t.append(" ▶ ", style="bold #00e5ff")
        t.append("A", style="bold #00e5ff")
        t.append("U", style="bold #38bdf8")
        t.append("R", style="bold #a855f7")
        t.append("A", style="bold #ec4899")
        t.append(" // CONTROL PLANE", style="bold white")
        t.append("   ", style="")
        t.append("AGENT ", style="dim")
        t.append(f"{agent_dot} {cfg.llm.provider.upper()}  ", style=f"bold {agent_color}")
        t.append("JEV ", style="dim")
        t.append(f"{jev_dot} [{jev_label}]  ", style=f"bold {jev_color}")
        t.append("AUDIT ", style="dim")
        t.append("[VALID]  ", style="bold green")
        t.append("LATTICE ", style="dim")
        t.append("[MONOTONE]  ", style="bold cyan")
        t.append("v0.2.0", style="dim magenta")
        return t


class StatusBar(Static):
    """Bottom status bar with active state and shortcuts."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: #060610;
        border-top: solid #1c1c34;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._status = "IDLE"
        self._run_id = "─"

    def set_status(self, status: str, run_id: Optional[str] = None) -> None:
        self._status = status
        if run_id:
            self._run_id = run_id
        self.refresh()

    def render(self) -> Text:
        cfg = get_config()
        jev_label = f"JEV: {'MOCK' if cfg.jev.mock_mode else cfg.jev.provider.upper()}"
        jev_color = "yellow" if cfg.jev.mock_mode else "green"
        t = Text()
        t.append(f" RUN: {self._run_id[:12]}  ", style="dim cyan")
        t.append(f"STATE: {self._status}  ", style="bold #a0a0b8")
        t.append(f"[{jev_label}]  ", style=f"bold {jev_color}")
        t.append("• [F1] Chat  [F2] Runs  [F3] Logs  [F4] Monitor  [F5] Policies  [F6] Settings • [ESC] Cancel", style="dim #707090")
        return t


class AURAApp(App):
    """AURA — Agent Control Plane Interactive TUI."""

    CSS = AURA_CSS

    BINDINGS = [
        Binding("f1", "goto_chat", "[F1] Chat", show=True),
        Binding("f2", "goto_runs", "[F2] Runs", show=True),
        Binding("f3", "goto_logs", "[F3] Logs", show=True),
        Binding("f4", "goto_monitor", "[F4] Monitor", show=True),
        Binding("f5", "goto_policies", "[F5] Policies", show=True),
        Binding("f6", "goto_settings", "[F6] Settings", show=True),
        Binding("ctrl+1", "goto_chat", "Chat", show=False),
        Binding("ctrl+2", "goto_runs", "Runs", show=False),
        Binding("ctrl+3", "goto_logs", "Logs", show=False),
        Binding("ctrl+4", "goto_monitor", "Monitor", show=False),
        Binding("ctrl+5", "goto_policies", "Policies", show=False),
        Binding("ctrl+6", "goto_settings", "Settings", show=False),
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("escape", "cancel_active_run", "Cancel", show=True),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.orchestrator: Optional[AURAOrchestrator] = None

    def compose(self) -> ComposeResult:
        yield AURAHeader(id="aura-header")
        with TabbedContent(initial="tab-chat", id="main-tabs"):
            with TabPane("⚡ [1] CHAT", id="tab-chat"):
                yield ChatView(id="view-chat")
            with TabPane("📋 [2] RUNS", id="tab-runs"):
                yield RunsView(id="view-runs")
            with TabPane("📜 [3] LOGS", id="tab-logs"):
                yield LogsView(id="view-logs")
            with TabPane("📊 [4] MONITOR", id="tab-monitor"):
                yield MonitorView(id="view-monitor")
            with TabPane("🛡️ [5] POLICIES", id="tab-policies"):
                yield PoliciesView(id="view-policies")
            with TabPane("⚙️ [6] SETTINGS", id="tab-settings"):
                yield SettingsView(id="view-settings")
        yield StatusBar(id="status-bar")

    async def on_mount(self) -> None:
        cfg = get_config()
        self.orchestrator = AURAOrchestrator(
            config=cfg,
            on_status_update=self._on_agent_status,
            on_approval_needed=self._on_approval_needed,
        )
        asyncio.create_task(self._initial_health_checks())

    def _on_approval_needed(self, data: Dict[str, Any]) -> None:
        """Trigger interactive pop-up modal when an action requires human approval."""
        from aura.ui.screens.approval_modal import ApprovalModalScreen
        modal = ApprovalModalScreen(
            approval_id=data.get("approval_id", ""),
            tool=data.get("tool", ""),
            args=data.get("args", {}),
            reason=data.get("reason", ""),
            assessment=data.get("assessment"),
            approval_manager=self.orchestrator.approval_manager if self.orchestrator else None,
        )
        self.push_screen(modal)

    def action_cancel_active_run(self) -> None:
        """ESC shortcut handler — cancel running agent and pending approvals."""
        try:
            view_chat = self.query_one("#view-chat", ChatView)
            view_chat.action_cancel_run()
        except Exception:
            if self.orchestrator:
                self.orchestrator.cancel()


    async def _initial_health_checks(self) -> None:
        if self.orchestrator:
            await self.orchestrator.health_check_provider()
            await self.orchestrator.health_check_jev()
            try:
                self.query_one("#aura-header", AURAHeader).refresh()
            except Exception:
                pass

    def _on_agent_status(self, msg: str) -> None:
        try:
            status_bar = self.query_one("#status-bar", StatusBar)
            run_id = None
            if self.orchestrator and self.orchestrator.current_run:
                run_id = self.orchestrator.current_run.run_id
            status_bar.set_status(msg[:24], run_id)
        except Exception:
            pass

    def switch_page(self, page_id: str) -> None:
        clean_id = page_id.replace("tab-", "")
        target = f"tab-{clean_id}"
        try:
            tabs = self.query_one("#main-tabs", TabbedContent)
            tabs.active = target
            # Trigger refresh hooks if applicable
            if clean_id == "runs":
                try:
                    self.query_one("#view-runs", RunsView).refresh_runs()
                except Exception:
                    pass
            elif clean_id == "monitor":
                try:
                    self.query_one("#view-monitor", MonitorView)._update_metrics()
                except Exception:
                    pass
        except Exception:
            pass

    # Navigation actions
    def action_goto_chat(self) -> None:
        self.switch_page("chat")

    def action_goto_runs(self) -> None:
        self.switch_page("runs")

    def action_goto_logs(self) -> None:
        self.switch_page("logs")

    def action_goto_monitor(self) -> None:
        self.switch_page("monitor")

    def action_goto_policies(self) -> None:
        self.switch_page("policies")

    def action_goto_settings(self) -> None:
        self.switch_page("settings")
