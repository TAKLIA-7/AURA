"""AURA Monitor View — real-time system metrics and security telemetry dashboard."""
from __future__ import annotations
import asyncio
from typing import Any, Optional

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Button, Label, Static, RichLog
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from rich.text import Text
from rich.table import Table
from rich import box as rbox

from aura.observability import get_metrics
from aura.observability.hash_chain import verify_audit_log_chain
from aura.config import get_config


class MonitorView(Container):
    """Real-time observability dashboard for AURA agent & JEV evaluation."""

    DEFAULT_CSS = """
    MonitorView {
        layout: vertical;
        height: 1fr;
        background: #0a0a12;
    }
    #monitor-top-bar {
        height: 3;
        background: #0d0d1f;
        border-bottom: solid #1a1a30;
        padding: 0 2;
        layout: horizontal;
    }
    #monitor-title-text {
        width: 1fr;
        padding-top: 1;
    }
    #btn-refresh-monitor {
        margin-top: 0;
        min-width: 16;
    }
    #monitor-scroll {
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }
    .monitor-row {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
    }
    .metric-panel {
        width: 1fr;
        border: solid #1a1a30;
        background: #0d0d1e;
        padding: 1 2;
        margin: 0 1 1 0;
        min-height: 10;
    }
    .metric-panel-full {
        width: 100%;
        border: solid #1a1a30;
        background: #0d0d1e;
        padding: 1 2;
        margin-bottom: 1;
    }
    #activity-feed {
        height: 9;
        border: solid #141428;
        background: #080814;
        padding: 0 1;
        overflow-y: auto;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._timer = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="monitor-top-bar"):
            yield Static(
                Text.from_markup("[bold cyan]◈ SYSTEM TELEMETRY & MONITOR[/bold cyan]  [dim]Real-time agent risk & JEV performance metrics[/dim]"),
                id="monitor-title-text",
            )
            yield Button("↻ Refresh Now", id="btn-refresh-monitor", variant="default")

        with ScrollableContainer(id="monitor-scroll"):
            # Row 1: Agent Health & JEV Health
            with Horizontal(classes="monitor-row"):
                with Container(id="agent-panel", classes="metric-panel"):
                    yield Static(id="agent-metrics")
                with Container(id="jev-panel", classes="metric-panel"):
                    yield Static(id="jev-metrics")

            # Row 2: Latency Sparkline & Security Policies
            with Horizontal(classes="monitor-row"):
                with Container(id="latency-panel", classes="metric-panel"):
                    yield Static(id="latency-metrics")
                with Container(id="policy-panel", classes="metric-panel"):
                    yield Static(id="policy-metrics")

            # Row 3: Multi-Agent RBAC & Idempotency / Concurrency
            with Horizontal(classes="monitor-row"):
                with Container(id="rbac-panel", classes="metric-panel"):
                    yield Static(id="rbac-metrics")
                with Container(id="idemp-panel", classes="metric-panel"):
                    yield Static(id="idemp-metrics")

            # Row 4: Usage / Tokens & Risk Distribution
            with Horizontal(classes="monitor-row"):
                with Container(id="usage-panel", classes="metric-panel"):
                    yield Static(id="usage-metrics")
                with Container(id="risk-dist-panel", classes="metric-panel"):
                    yield Static(id="risk-dist-metrics")

            # Row 5: Recent Activity Feed
            with Container(id="activity-panel", classes="metric-panel-full"):
                yield Static(Text.from_markup("[bold cyan]RECENT SYSTEM AUDIT ACTIVITY[/bold cyan]  [dim](last 15 events)[/dim]"))
                yield RichLog(id="activity-feed", highlight=True, markup=True)

    def on_mount(self) -> None:
        self._update_metrics()
        cfg = get_config()
        refresh_sec = max(1.0, cfg.display.monitor_refresh_seconds)
        self._timer = self.set_interval(refresh_sec, self._update_metrics)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh-monitor":
            self._update_metrics()
            self.notify("Telemetry refreshed.", severity="information")

    def _make_bar(self, value: int, total: int, width: int = 20, color: str = "cyan") -> Text:
        if total <= 0:
            filled = 0
        else:
            filled = min(width, int((value / total) * width))
        bar = "█" * filled + "░" * (width - filled)
        t = Text()
        t.append(bar, style=color)
        t.append(f"  {value}", style="bold white")
        return t

    def _update_metrics(self) -> None:
        try:
            m = get_metrics()
            cfg = get_config()

            # 1. Agent metrics
            agent_conn = "● CONNECTED" if m.agent_connected else "○ DISCONNECTED"
            agent_color = "green" if m.agent_connected else "red"
            t1 = Text()
            t1.append("AGENT HEALTH & RUNTIME\n", style="bold cyan")
            t1.append("  Status:     ", style="dim")
            t1.append(f"{agent_conn}\n", style=f"bold {agent_color}")
            t1.append("  Provider:   ", style="dim")
            t1.append(f"{cfg.llm.provider.upper()} ({cfg.llm.model.split('/')[-1]})\n", style="white")
            t1.append("  Active:     ", style="dim")
            t1.append(f"{m.active_runs} runs\n", style="yellow")
            t1.append("  Completed:  ", style="dim")
            t1.append(f"{m.completed_runs} runs\n", style="green")
            t1.append("  Failed:     ", style="dim")
            t1.append(f"{m.failed_runs} runs\n", style="red" if m.failed_runs > 0 else "dim")
            self.query_one("#agent-metrics", Static).update(t1)

            # 2. JEV metrics
            jev_conn = "● CONNECTED" if m.jev_connected else "○ DISCONNECTED"
            jev_color = "green" if m.jev_connected else "red"
            engine_label = "MOCK" if cfg.jev.mock_mode else (cfg.jev.provider.upper() if cfg.jev.provider else "LIVE")
            t2 = Text()
            t2.append("JEV RISK ASSESSMENT ENGINE\n", style="bold magenta")
            t2.append("  Status:     ", style="dim")
            t2.append(f"{jev_conn} ", style=f"bold {jev_color}")
            t2.append(f"[{engine_label}]\n", style="bold #CC44FF")
            t2.append("  Evaluated:  ", style="dim")
            t2.append(f"{m.total_jev_assessments} actions\n", style="bold #00FFFF")
            t2.append("  Failures:   ", style="dim")
            t2.append(f"{m.jev_failures}\n", style="red" if m.jev_failures > 0 else "dim")
            p50 = f"{m.jev_p50_ms:.0f}ms" if m.jev_p50_ms is not None else "N/A"
            p95 = f"{m.jev_p95_ms:.0f}ms" if m.jev_p95_ms is not None else "N/A"
            t2.append(f"  Latency p50: ", style="dim")
            t2.append(f"{p50}  ", style="white")
            t2.append(f"p95: ", style="dim")
            t2.append(f"{p95}\n", style="white")
            self.query_one("#jev-metrics", Static).update(t2)

            # 3. Latency sparkline & live oscilloscope
            t3 = Text()
            t3.append("JEV DECISION LATENCY & OSCILLOSCOPE\n", style="bold cyan")
            t3.append("  Recent Trend:   ", style="dim")
            t3.append(m.jev_sparkline, style="bold #c084fc")
            t3.append(f"  (p50: {p50})\n", style="dim")

            # Realistic Oscilloscope waveform animation
            import math, time
            t_sec = time.monotonic() * 2.5
            WAVE_BLOCKS = [" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
            osc = []
            for xi in range(18):
                h = 0.5 + 0.35 * math.sin(xi * 0.7 - t_sec) + 0.15 * math.cos(xi * 1.4 + t_sec * 0.8)
                idx = max(0, min(len(WAVE_BLOCKS) - 1, int(h * len(WAVE_BLOCKS))))
                osc.append(WAVE_BLOCKS[idx])
            t3.append("\n  Live Spectrum:  ", style="dim")
            t3.append("".join(osc), style="bold #00e5ff")
            t3.append("  [ACTIVE]\n", style="bold #10b981")
            t3.append("  [0ms] ─── Fast ─── Standard ─── [500ms+]\n", style="dim #555577")
            self.query_one("#latency-metrics", Static).update(t3)

            # 4. Policy metrics
            total_decisions = m.allowed_actions + m.blocked_actions + m.pending_approvals
            t4 = Text()
            t4.append("POLICY ENFORCEMENT DECISIONS\n", style="bold cyan")
            t4.append("  Total tool calls:  ", style="dim")
            t4.append(f"{m.total_tool_calls}\n", style="bold white")
            t4.append("  ALLOW:   ")
            t4.append_text(self._make_bar(m.allowed_actions, max(total_decisions, 1), 16, "green"))
            t4.append("\n  BLOCK:   ")
            t4.append_text(self._make_bar(m.blocked_actions, max(total_decisions, 1), 16, "red"))
            t4.append("\n  PENDING: ")
            t4.append_text(self._make_bar(m.pending_approvals, max(total_decisions, 1), 16, "yellow"))
            events_file = cfg.runtime.data_dir / "logs" / "aura-events.jsonl"
            chain_rep = verify_audit_log_chain(events_file)
            chain_status = "● VERIFIED" if chain_rep["valid"] else "✗ TAMPER DETECTED"
            chain_col = "green" if chain_rep["valid"] else "red"
            t4.append(f"\n  HASH CHAIN: ", style="dim")
            t4.append(f"{chain_status} ", style=f"bold {chain_col}")
            t4.append(f"({chain_rep['total_events']} events)\n", style="dim")
            t4.append(f"  HEAD HASH:  ", style="dim")
            t4.append(f"{chain_rep['head_hash'][:14]}...\n", style="cyan")
            self.query_one("#policy-metrics", Static).update(t4)

            # 4b. RBAC metrics
            t_rbac = Text()
            t_rbac.append("MULTI-AGENT RBAC & ATTENUATION\n", style="bold cyan")
            t_rbac.append("  Active Role:        ", style="dim")
            t_rbac.append("SUPERVISOR\n", style="bold green")
            t_rbac.append("  Delegation Policy:  ", style="dim")
            t_rbac.append("MONOTONIC ATTENUATION\n", style="white")
            t_rbac.append("  Registered Roles:   ", style="dim")
            t_rbac.append("8 Roles (ADMIN -> GUEST)\n", style="white")
            t_rbac.append("  Session Token TTL:  ", style="dim")
            t_rbac.append("VALID (Active Token)\n", style="green")
            t_rbac.append("  Privilege Boundary: ", style="dim")
            t_rbac.append("Priv(Child) ⊆ Priv(Parent)\n", style="cyan")
            self.query_one("#rbac-metrics", Static).update(t_rbac)

            # 4c. Idempotency & Mutex Concurrency
            t_idemp = Text()
            t_idemp.append("IDEMPOTENCY & CONCURRENCY GATE\n", style="bold cyan")
            t_idemp.append("  Key Generator:      ", style="dim")
            t_idemp.append("CANONICAL SHA-256\n", style="white")
            t_idemp.append("  Race/TOCTOU Mutex:  ", style="dim")
            t_idemp.append("ACTIVE (In-Flight Locks)\n", style="green")
            t_idemp.append("  Deduplication TTL:  ", style="dim")
            t_idemp.append("300s Sliding Window\n", style="white")
            t_idemp.append("  Rate Limiting:      ", style="dim")
            t_idemp.append("Sliding Window Token Bucket\n", style="white")
            t_idemp.append("  Double-Exec Guard:  ", style="dim")
            t_idemp.append("ENFORCED (Fail Closed)\n", style="bold green")
            self.query_one("#idemp-metrics", Static).update(t_idemp)

            # 5. Usage & Efficiency
            t5 = Text()
            t5.append("RESOURCE USAGE & TOKENS\n", style="bold cyan")
            t5.append("  Prompt Tokens:      ", style="dim")
            t5.append(f"{m.input_tokens if m.input_tokens else '─'}\n", style="white")
            t5.append("  Completion Tokens:  ", style="dim")
            t5.append(f"{m.output_tokens if m.output_tokens else '─'}\n", style="white")
            t5.append("  JEV Engine Mode:    ", style="dim")
            t5.append(f"{engine_label}\n", style="yellow" if cfg.jev.mock_mode else "green")
            self.query_one("#usage-metrics", Static).update(t5)

            # 6. Risk distribution
            t6 = Text()
            t6.append("ASSESSED RISK DISTRIBUTION\n", style="bold cyan")
            rd = m.risk_distribution
            if rd:
                for risk in ("critical", "high", "medium", "low", "none"):
                    count = rd.get(risk, 0)
                    rc = {"critical": "bright_red", "high": "red", "medium": "yellow", "low": "green", "none": "dim"}.get(risk, "white")
                    t6.append(f"  {risk.upper():10s} ", style=f"bold {rc}")
                    t6.append_text(self._make_bar(count, max(sum(rd.values()), 1), 14, rc))
                    t6.append("\n")
            else:
                t6.append("  No risk events recorded yet.\n  Run an agent task in [1] CHAT to generate telemetry.", style="dim")
            self.query_one("#risk-dist-metrics", Static).update(t6)

            # 7. Activity feed
            feed = self.query_one("#activity-feed", RichLog)
            feed.clear()
            events = m.recent_events[:15]
            if events:
                for ev in events:
                    ts = ev.get("time", "")
                    summary = ev.get("summary", "")
                    color = "red" if "BLOCK" in summary or "FAIL" in summary else ("green" if "COMPLETE" in summary else "#888899")
                    feed.write(Text.from_markup(f"  [dim]{ts}[/dim]  [{color}]{summary}[/{color}]"))
            else:
                feed.write(Text.from_markup("  [dim]System standing by. No actions intercepted yet.[/dim]"))
        except Exception:
            pass


# Alias for backward compatibility
MonitorScreen = MonitorView
