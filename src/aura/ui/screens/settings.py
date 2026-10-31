"""AURA Settings Screen — Interactive Provider, JEV, Display, and Diagnostics Hub."""
from __future__ import annotations
import asyncio
import os
from typing import Any

from textual.app import ComposeResult
from textual.widgets import Button, Static
from textual.containers import Container, Horizontal, VerticalScroll
from rich.text import Text

from aura.config import get_config
from aura.multiagent.llm_factory import MODELS


class SettingsView(Container):
    DEFAULT_CSS = """
    SettingsView {
        background: #0a0a12;
        layout: vertical;
        height: 1fr;
    }
    #settings-header {
        height: 3;
        background: #0d0d1f;
        padding: 0 2;
        border-bottom: solid #1a1a30;
    }
    #settings-scroll {
        height: 1fr;
        padding: 1 2;
        overflow-y: scroll;
    }
    .settings-section {
        height: auto;
        border: solid #1a1a30;
        background: #0d0d1e;
        padding: 1 2;
        margin: 0 0 1 0;
    }
    .settings-title {
        color: #00FFFF;
        text-style: bold;
        margin-bottom: 1;
    }
    .button-row {
        height: auto;
        margin-top: 1;
        layout: horizontal;
    }
    .button-row Button {
        margin-right: 1;
        margin-bottom: 1;
        height: 3;
    }
    """

    def compose(self) -> ComposeResult:
        cfg = get_config()
        with Container(id="settings-header"):
            yield Static(Text.from_markup("[bold cyan]◈ SETTINGS[/bold cyan]  [dim]Provider, JEV, and runtime configuration[/dim]"))
        with VerticalScroll(id="settings-scroll"):
            # 1. LLM Provider
            with Container(id="llm-section", classes="settings-section"):
                yield Static(Text.from_markup("[bold cyan]LLM PROVIDER & MODEL SWITCHER[/bold cyan]"), classes="settings-title")
                yield Static(Text.from_markup(f"  Active Provider: [cyan]{cfg.llm.provider.upper()}[/cyan]"), id="cfg-llm-provider")
                yield Static(Text.from_markup(f"  Active Model:    [cyan]{cfg.llm.model}[/cyan]"), id="cfg-llm-model")
                yield Static(Text.from_markup(f"  API Key:         [dim]{'● Configured' if cfg.llm.api_key else '○ Not configured (set OPENROUTER_API_KEY or GEMINI_API_KEY)'}[/dim]"))
                yield Static(Text.from_markup("  [dim]Quickly switch active model:[/dim]"))
                with Horizontal(classes="button-row"):
                    yield Button("Model A (Seedream)", id="btn-model-a")
                    yield Button("Model B (Claude)", id="btn-model-b")
                    yield Button("Model C (Hunyuan)", id="btn-model-c")
                    yield Button("Model D (DeepSeek)", id="btn-model-d")
                    yield Button("Gemini Flash", id="btn-model-gemini")

            # 2. JEV Risk Engine
            with Container(id="jev-section", classes="settings-section"):
                yield Static(Text.from_markup("[bold magenta]JEV RISK ENGINE[/bold magenta]"), classes="settings-title")
                jev_label, jev_color = self._get_jev_label()
                yield Static(Text.from_markup(f"  Engine Mode:     [{jev_color}]{jev_label}[/{jev_color}]"), id="cfg-jev-status")
                yield Static(Text.from_markup(f"  Endpoint:        [cyan]{cfg.jev.endpoint or 'Default (OpenRouter/Mock)'}[/cyan]"))
                yield Static(Text.from_markup(f"  API Key:         [dim]{'● Configured' if cfg.jev.api_key else '○ Not configured'}[/dim]"))
                yield Static(Text.from_markup(f"  Timeout:         [white]{cfg.jev.timeout_seconds}s[/white]"))
                with Horizontal(classes="button-row"):
                    yield Button("Toggle Live / Mock JEV", id="btn-toggle-jev")

            # 3. Runtime
            with Container(id="runtime-section", classes="settings-section"):
                yield Static(Text.from_markup("[bold cyan]RUNTIME SETTINGS[/bold cyan]"), classes="settings-title")
                yield Static(Text.from_markup(f"  Data dir:          [cyan]{cfg.runtime.data_dir}[/cyan]"))
                yield Static(Text.from_markup(f"  Workspace root:    [cyan]{cfg.runtime.workspace_root}[/cyan]"))
                yield Static(Text.from_markup(f"  Max agent turns:   [white]{cfg.runtime.max_agent_turns}[/white]"))
                yield Static(Text.from_markup(f"  Max tool calls:    [white]{cfg.runtime.max_tool_calls}[/white]"))
                yield Static(Text.from_markup(f"  Agent timeout:     [white]{cfg.runtime.agent_timeout_seconds}s[/white]"))
                yield Static(Text.from_markup(f"  Monitor refresh:   [white]{cfg.display.monitor_refresh_seconds}s[/white]"))

            # 4. Terminal UI & Display
            with Container(id="display-section", classes="settings-section"):
                yield Static(Text.from_markup("[bold cyan]TERMINAL UI & DISPLAY[/bold cyan]"), classes="settings-title")
                yield Static(Text.from_markup(f"  Tool Display:      [cyan]{cfg.display.tool_display.upper()}[/cyan]  [dim](grouped | emoji | minimal | hidden)[/dim]"), id="cfg-tool-display")
                yield Static(Text.from_markup(f"  Loader Animation:  [cyan]{cfg.display.loader_style.upper()}[/cyan]  [dim](gradient shimmer | spinner | minimal)[/dim]"), id="cfg-loader-style")
                yield Static(Text.from_markup(f"  Input Style:       [cyan]{cfg.display.input_style.upper()}[/cyan]  [dim](bordered | block | plain)[/dim]"), id="cfg-input-style")
                with Horizontal(classes="button-row"):
                    yield Button("Cycle Tool Display", id="btn-toggle-tool-display")
                    yield Button("Cycle Loader", id="btn-toggle-loader")
                    yield Button("Cycle Input Style", id="btn-toggle-input-style")

            # 5. Connectivity Diagnostics
            with Container(id="connectivity-section", classes="settings-section"):
                yield Static(Text.from_markup("[bold cyan]CONNECTIVITY DIAGNOSTICS[/bold cyan]"), classes="settings-title")
                yield Static(Text.from_markup("  [dim]Click below to run live network diagnostic probes.[/dim]"))
                yield Static("", id="connectivity-status")
                with Horizontal(classes="button-row"):
                    yield Button("Run Diagnostics", id="btn-diag", variant="primary")

    def _get_jev_label(self) -> tuple[str, str]:
        cfg = get_config()
        if cfg.jev.mock_mode:
            return "⚠ MOCK MODE", "yellow"
        elif cfg.jev.provider == "openrouter":
            return f"● OPENROUTER ({cfg.jev.model.split('/')[-1]})", "green"
        return "● LIVE (JEV ENDPOINT)", "green"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        cfg = get_config()
        btn_id = event.button.id

        # Model Switching
        model_map = {
            "btn-model-a": ("A", MODELS["A"], "openrouter"),
            "btn-model-b": ("B", MODELS["B"], "openrouter"),
            "btn-model-c": ("C", MODELS["C"], "openrouter"),
            "btn-model-d": ("D", MODELS["D"], "openrouter"),
            "btn-model-gemini": ("gemini", MODELS["gemini"], "gemini"),
        }
        if btn_id in model_map:
            alias, model_slug, provider = model_map[btn_id]
            cfg.llm.model = model_slug
            cfg.llm.provider = provider
            os.environ["MODEL"] = alias
            os.environ["AURA_MODEL"] = alias
            self.query_one("#cfg-llm-provider", Static).update(
                Text.from_markup(f"  Active Provider: [cyan]{cfg.llm.provider.upper()}[/cyan]")
            )
            self.query_one("#cfg-llm-model", Static).update(
                Text.from_markup(f"  Active Model:    [cyan]{cfg.llm.model}[/cyan]")
            )
            self._refresh_header()
            self.notify(f"Switched model to: {model_slug} ({alias})", severity="information")
            return

        # JEV Toggle
        if btn_id == "btn-toggle-jev":
            cfg.jev.mock_mode = not cfg.jev.mock_mode
            os.environ["AURA_JEV_MOCK_MODE"] = "true" if cfg.jev.mock_mode else "false"
            label, color = self._get_jev_label()
            self.query_one("#cfg-jev-status", Static).update(
                Text.from_markup(f"  Engine Mode:     [{color}]{label}[/{color}]")
            )
            self._refresh_header()
            self.notify(f"JEV Engine set to: {label}", severity="information")
            return

        # Diagnostics
        if btn_id == "btn-diag":
            asyncio.create_task(self._run_diagnostics())
            return

        # Display Toggles
        if btn_id == "btn-toggle-tool-display":
            modes = ["grouped", "emoji", "minimal", "hidden"]
            cur_idx = modes.index(cfg.display.tool_display) if cfg.display.tool_display in modes else 0
            cfg.display.tool_display = modes[(cur_idx + 1) % len(modes)]
            self.query_one("#cfg-tool-display", Static).update(
                Text.from_markup(f"  Tool Display:      [cyan]{cfg.display.tool_display.upper()}[/cyan]  [dim](grouped | emoji | minimal | hidden)[/dim]")
            )
            self.notify(f"Tool display set to: {cfg.display.tool_display}", severity="information")
        elif btn_id == "btn-toggle-loader":
            styles = ["gradient", "spinner", "minimal"]
            cur_idx = styles.index(cfg.display.loader_style) if cfg.display.loader_style in styles else 0
            cfg.display.loader_style = styles[(cur_idx + 1) % len(styles)]
            self.query_one("#cfg-loader-style", Static).update(
                Text.from_markup(f"  Loader Animation:  [cyan]{cfg.display.loader_style.upper()}[/cyan]  [dim](gradient shimmer | spinner | minimal)[/dim]")
            )
            self.notify(f"Loader style set to: {cfg.display.loader_style}", severity="information")
        elif btn_id == "btn-toggle-input-style":
            inputs = ["bordered", "block", "plain"]
            cur_idx = inputs.index(cfg.display.input_style) if cfg.display.input_style in inputs else 0
            cfg.display.input_style = inputs[(cur_idx + 1) % len(inputs)]
            self.query_one("#cfg-input-style", Static).update(
                Text.from_markup(f"  Input Style:       [cyan]{cfg.display.input_style.upper()}[/cyan]  [dim](bordered | block | plain)[/dim]")
            )
            self.notify(f"Input style set to: {cfg.display.input_style}", severity="information")

    def _refresh_header(self) -> None:
        try:
            header = self.app.query_one("#aura-header")
            if header:
                header.refresh()
            status_bar = self.app.query_one("#status-bar")
            if status_bar:
                status_bar.refresh()
        except Exception:
            pass

    async def _run_diagnostics(self) -> None:
        status = self.query_one("#connectivity-status", Static)
        status.update(Text.from_markup("  [yellow]Running diagnostics...[/yellow]"))
        app = self.app
        cfg = get_config()
        results = []

        if hasattr(app, "orchestrator") and app.orchestrator:
            provider_ok = await app.orchestrator.health_check_provider()
            jev_ok = await app.orchestrator.health_check_jev()
            p_name = cfg.llm.provider.capitalize()
            j_name = "OPENROUTER" if (cfg.jev.provider == "openrouter" and not cfg.jev.mock_mode) else ("MOCK" if cfg.jev.mock_mode else "LIVE")
            results.append(f"  Agent Provider ({p_name}): {'● OK' if provider_ok else '✗ FAILED / NO KEY'}")
            results.append(f"  JEV Risk Engine ({j_name}): {'● OK' if jev_ok else '✗ FAILED'}")
        else:
            results.append("  Orchestrator not ready yet.")

        t = Text()
        for r in results:
            color = "green" if "● OK" in r else "red"
            t.append(f"{r}\n", style=color)
        status.update(t)


# Alias for backward compatibility
SettingsScreen = SettingsView

