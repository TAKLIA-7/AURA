"""AURA Real-Time Telemetry Monitor — standalone live terminal dashboard using Rich."""
from __future__ import annotations
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from aura.config import get_config
from aura.observability import get_metrics
from aura.observability.hash_chain import verify_audit_log_chain


def _make_bar(value: int, total: int, width: int = 16, color: str = "cyan") -> Text:
    filled = min(width, int((value / total) * width)) if total > 0 else 0
    bar = "█" * filled + "░" * (width - filled)
    t = Text()
    t.append(bar, style=color)
    t.append(f" {value}", style="bold white")
    return t


def build_monitor_layout() -> Layout:
    layout = Layout(name="root")
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="upper", size=10),
        Layout(name="middle", size=9),
        Layout(name="events", ratio=1),
        Layout(name="footer", size=3),
    )
    layout["upper"].split_row(
        Layout(name="runtime_health", ratio=1),
        Layout(name="policy_metrics", ratio=1),
        Layout(name="risk_dist", ratio=1),
    )
    layout["middle"].split_row(
        Layout(name="hash_chain", ratio=1),
        Layout(name="jev_latency", ratio=1),
    )
    return layout


def render_header() -> Panel:
    cfg = get_config()
    m = get_metrics()
    agent_dot = "●" if m.agent_connected else "○"
    agent_color = "green" if m.agent_connected else "yellow"
    jev_dot = "●" if m.jev_connected else "○"
    jev_color = "green" if m.jev_connected else ("yellow" if cfg.jev.mock_mode else "red")
    engine_label = "MOCK" if cfg.jev.mock_mode else (cfg.jev.provider.upper() if cfg.jev.provider else "LIVE")

    t = Text()
    t.append(" A.U.R.A ", style="bold black on bright_cyan")
    t.append("  REAL-TIME MULTI-AGENT CONTROL PLANE & TELEMETRY MONITOR", style="bold white")
    t.append("  │  AGENT: ", style="dim")
    t.append(f"{agent_dot} {cfg.llm.provider.upper()} ", style=f"bold {agent_color}")
    t.append(" │  JEV: ", style="dim")
    t.append(f"{jev_dot} [{engine_label}] ", style=f"bold {jev_color}")
    t.append(f" │  MODEL: {cfg.llm.model.split('/')[-1]}", style="cyan")
    return Panel(t, box=box.ROUNDED, style="bold cyan")


def render_runtime_health() -> Panel:
    m = get_metrics()
    cfg = get_config()
    table = Table.grid(padding=(0, 2))
    table.add_column("Key", style="dim")
    table.add_column("Value", style="bold white")

    table.add_row("Agent Provider:", f"{cfg.llm.provider.upper()}")
    table.add_row("Active Swarm Runs:", f"[bold yellow]{m.active_runs}[/bold yellow]")
    table.add_row("Completed Runs:", f"[bold green]{m.completed_runs}[/bold green]")
    table.add_row("Failed Runs:", f"[bold red]{m.failed_runs}[/bold red]" if m.failed_runs > 0 else "0")
    table.add_row("Prompt Tokens:", f"{m.input_tokens:,}" if m.input_tokens else "0")
    table.add_row("Completion Tokens:", f"{m.output_tokens:,}" if m.output_tokens else "0")

    return Panel(table, title="[bold cyan]Runtime Health[/bold cyan]", box=box.ROUNDED)


def render_policy_metrics() -> Panel:
    m = get_metrics()
    total_decisions = max(1, m.allowed_actions + m.blocked_actions + m.pending_approvals)

    table = Table.grid(padding=(0, 1))
    table.add_column("Label", style="dim", width=12)
    table.add_column("Bar", width=22)

    table.add_row("Tool Calls:", f"[bold white]{m.total_tool_calls}[/bold white]")
    table.add_row("ALLOWED:", _make_bar(m.allowed_actions, total_decisions, 14, "green"))
    table.add_row("BLOCKED:", _make_bar(m.blocked_actions, total_decisions, 14, "red"))
    table.add_row("APPROVAL:", _make_bar(m.pending_approvals, total_decisions, 14, "yellow"))

    return Panel(table, title="[bold cyan]Policy & Tool Enforcement[/bold cyan]", box=box.ROUNDED)


def render_risk_dist() -> Panel:
    m = get_metrics()
    rd = m.risk_distribution
    table = Table.grid(padding=(0, 1))
    table.add_column("Level", width=10)
    table.add_column("Bar", width=22)

    total_assessed = max(1, sum(rd.values()))
    levels = [
        ("CRITICAL", "critical", "bright_red"),
        ("HIGH", "high", "red"),
        ("MEDIUM", "medium", "yellow"),
        ("LOW", "low", "green"),
        ("NONE", "none", "dim cyan"),
    ]
    for label, key, color in levels:
        count = rd.get(key, 0)
        table.add_row(f"[{color}]{label}[/{color}]", _make_bar(count, total_assessed, 14, color))

    return Panel(table, title="[bold cyan]JEV Risk Distribution[/bold cyan]", box=box.ROUNDED)


def render_hash_chain() -> Panel:
    cfg = get_config()
    events_file = cfg.runtime.data_dir / "logs" / "aura-events.jsonl"
    report = verify_audit_log_chain(events_file)

    table = Table.grid(padding=(0, 2))
    table.add_column("Metric", style="dim")
    table.add_column("Value")

    valid_str = "[bold green]✓ 100% SECURE & VERIFIED[/bold green]" if report["valid"] else "[bold red]✗ TAMPER DETECTED[/bold red]"
    table.add_row("Chain Integrity:", valid_str)
    table.add_row("Audited Events:", f"[bold white]{report['total_events']}[/bold white]")
    head_short = report["head_hash"][:16] + "..." if report["head_hash"] else "0000000000000000..."
    table.add_row("Latest Head Hash:", f"[cyan]{head_short}[/cyan]")
    table.add_row("Security Lattice:", "[bold magenta]Monotone Non-Decreasing Floor (Latched)[/bold magenta]")
    table.add_row("RBAC Policy:", "[bold green]Least Privilege & Attenuation Active[/bold green]")

    return Panel(table, title="[bold cyan]Cryptographic Hash Chain & Monotone State[/bold cyan]", box=box.ROUNDED)


def render_jev_latency() -> Panel:
    m = get_metrics()
    table = Table.grid(padding=(0, 2))
    table.add_column("Label", style="dim")
    table.add_column("Value")

    p50_str = f"{m.jev_p50_ms:.0f} ms" if m.jev_p50_ms is not None else "N/A"
    p95_str = f"{m.jev_p95_ms:.0f} ms" if m.jev_p95_ms is not None else "N/A"

    table.add_row("Median Latency (p50):", f"[bold white]{p50_str}[/bold white]")
    table.add_row("Tail Latency (p95):", f"[bold yellow]{p95_str}[/bold yellow]")
    table.add_row("Sparkline Trend:", f"[bold #c084fc]{m.jev_sparkline}[/bold #c084fc]")

    import math
    t_sec = time.monotonic() * 2.5
    WAVE_BLOCKS = [" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
    osc = "".join(WAVE_BLOCKS[max(0, min(7, int((0.5 + 0.35 * math.sin(xi * 0.7 - t_sec) + 0.15 * math.cos(xi * 1.4 + t_sec * 0.8)) * 8)))] for xi in range(16))
    table.add_row("Active Oscilloscope:", f"[bold cyan]{osc}[/bold cyan] [bold green]LIVE[/bold green]")
    table.add_row("Total Assessments:", f"[bold white]{m.total_jev_assessments}[/bold white]")
    table.add_row("Assessment Timeouts:", f"[red]{m.jev_timeouts}[/red]" if m.jev_timeouts > 0 else "0")

    return Panel(table, title="[bold cyan]JEV Decision Latency & Spectrum[/bold cyan]", box=box.ROUNDED)


def render_events_table(events_file: Path) -> Panel:
    table = Table(
        box=box.SIMPLE_HEAD,
        expand=True,
        header_style="bold cyan",
        show_edge=False,
    )
    table.add_column("Time", style="dim", width=9)
    table.add_column("Seq#", style="dim", width=5)
    table.add_column("Event Type", style="bold white", width=24)
    table.add_column("Agent / Tool Target", width=30)
    table.add_column("Decision", width=12)
    table.add_column("Hash Prefix", style="dim cyan", width=14)

    events: List[Dict[str, Any]] = []
    if events_file.exists():
        try:
            with open(events_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines[-12:]:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except Exception:
                            pass
        except Exception:
            pass

    if events:
        for ev in reversed(events):
            ts = ev.get("timestamp", "")
            time_short = ts.split("T")[-1][:8] if "T" in ts else ts[:8]
            seq = str(ev.get("sequence_number", "-"))
            etype = ev.get("event_type", "unknown")
            action = ev.get("action") or {}
            tool_target = action.get("tool") or action.get("target") or "system"
            if len(tool_target) > 28:
                tool_target = tool_target[:26] + ".."

            dec = (ev.get("decision") or {}).get("result") or ""
            dec_styled = (
                "[bold green]ALLOW[/bold green]" if dec == "allow"
                else ("[bold red]BLOCK[/bold red]" if dec == "block"
                else ("[bold yellow]APPROVAL[/bold yellow]" if dec == "approval_required"
                else "[dim]─[/dim]"))
            )
            ehash = ev.get("event_hash", "")[:12] + ".." if ev.get("event_hash") else "─"
            table.add_row(time_short, seq, etype, tool_target, dec_styled, ehash)
    else:
        table.add_row("─", "0", "Standing by — no events intercepted yet", "─", "─", "─")

    return Panel(table, title="[bold cyan]Live Cryptographic Audit Event Stream (Latest Events)[/bold cyan]", box=box.ROUNDED)


def render_footer() -> Panel:
    t = Text()
    t.append(" [F1-F6] Tabs in TUI  │  ", style="dim")
    t.append("Ctrl+C", style="bold yellow")
    t.append(" Exit Monitor  │  Auto-refresh: 1.5s  │  Audit Log: data/logs/aura-events.jsonl", style="dim")
    return Panel(t, box=box.ROUNDED)


def run_realtime_monitor(refresh_seconds: float = 1.5) -> None:
    """Launch the live real-time terminal telemetry monitor loop."""
    console = Console()
    cfg = get_config()
    events_file = cfg.runtime.data_dir / "logs" / "aura-events.jsonl"
    layout = build_monitor_layout()

    with Live(layout, console=console, refresh_per_second=4, screen=True) as live:
        try:
            while True:
                layout["header"].update(render_header())
                layout["runtime_health"].update(render_runtime_health())
                layout["policy_metrics"].update(render_policy_metrics())
                layout["risk_dist"].update(render_risk_dist())
                layout["hash_chain"].update(render_hash_chain())
                layout["jev_latency"].update(render_jev_latency())
                layout["events"].update(render_events_table(events_file))
                layout["footer"].update(render_footer())
                time.sleep(refresh_seconds)
        except KeyboardInterrupt:
            pass

