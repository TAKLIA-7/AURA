"""AURA Textual CSS theme — modern cyber-aesthetic design system."""

AURA_CSS = """
Screen {
    background: #080812;
}

Header {
    background: #0c0c1e;
    color: #00e5ff;
    height: 3;
}

Footer {
    background: #0c0c1e;
    color: #8888aa;
    height: 1;
}

TabbedContent {
    background: #080812;
    height: 1fr;
}

Tabs {
    background: #0b0b1c;
    height: 3;
    border-bottom: solid #1e1e38;
}

Tab {
    color: #777799;
    padding: 0 2;
    height: 3;
    background: #0b0b1c;
    text-style: none;
    transition: color 150ms;
}

Tab:hover {
    color: #00e5ff;
    background: #14142f;
}

Tab.-active {
    color: #00e5ff;
    background: #181836;
    text-style: bold;
    border-bottom: tall #00e5ff;
}

TabPane {
    background: #080812;
    padding: 0;
    height: 1fr;
}

.panel {
    border: solid #222244;
    background: #0d0d22;
    padding: 1 2;
}

.panel-title {
    color: #00e5ff;
    text-style: bold;
}

.status-bar {
    background: #060610;
    color: #8888aa;
    height: 1;
    padding: 0 1;
    border-top: solid #1c1c34;
}

.jev-badge {
    color: #c084fc;
}

.success {
    color: #10b981;
}

.warning {
    color: #f59e0b;
}

.error {
    color: #f43f5e;
}

.blocked {
    color: #f43f5e;
    text-style: bold;
}

.allowed {
    color: #10b981;
    text-style: bold;
}

.pending {
    color: #f59e0b;
}

.muted {
    color: #555577;
}

.agent-text {
    color: #e2e8f0;
}

.user-text {
    color: #93c5fd;
    text-style: bold;
}

.tool-name {
    color: #00e5ff;
    text-style: bold;
}

.risk-high {
    color: #f43f5e;
}

.risk-medium {
    color: #f59e0b;
}

.risk-low {
    color: #10b981;
}

.risk-none {
    color: #64748b;
}

Input {
    background: #0e0e24;
    border: tall #232348;
    color: #f1f5f9;
    padding: 0 2;
}

Input:focus {
    border: tall #00e5ff;
}

Button {
    background: #161632;
    color: #00e5ff;
    border: solid #282852;
    min-height: 1;
    padding: 0 2;
    text-style: bold;
}

Button:hover {
    background: #242450;
    border: solid #00e5ff;
    color: #ffffff;
}

Button.danger {
    background: #350818;
    color: #f43f5e;
    border: solid #551228;
}

Button.danger:hover {
    background: #551228;
    border: solid #f43f5e;
    color: #ffffff;
}

Button.success {
    background: #08281a;
    color: #10b981;
    border: solid #12442e;
}

Button.success:hover {
    background: #12442e;
    border: solid #10b981;
    color: #ffffff;
}

DataTable {
    background: #0c0c20;
    border: solid #1e1e3a;
}

DataTable > .datatable--header {
    background: #0f0f2a;
    color: #00e5ff;
    text-style: bold;
}

DataTable > .datatable--cursor {
    background: #1e1e48;
    color: #ffffff;
}

RichLog {
    background: #080816;
    border: solid #1a1a36;
}

Label {
    color: #94a3b8;
}

/* Quick Action Suggestion Chips */
#quick-actions-bar {
    height: 3;
    padding: 0 1;
    layout: horizontal;
    background: #0b0b1c;
    border-top: solid #1c1c34;
}

.quick-chip {
    height: 1;
    margin: 1 1 0 0;
    min-width: 14;
    background: #12122c;
    color: #93c5fd;
    border: solid #222248;
    padding: 0 1;
}

.quick-chip:hover {
    background: #1d1d44;
    border: solid #00e5ff;
    color: #00e5ff;
}

/* Input style variations */
.input-bordered {
    background: transparent;
    border: none;
    padding: 0 1;
}

.input-block {
    background: #0e0e24;
    border: tall #232348;
    padding: 0 1;
}

.input-block:focus-within {
    border: tall #00e5ff;
}

.input-plain {
    background: transparent;
    border: none;
    padding: 0;
}

.chip-tag {
    background: #161634;
    color: #00e5ff;
    padding: 0 1;
    margin-right: 1;
}

.chip-dim {
    background: #111124;
    color: #64748b;
    padding: 0 1;
}
"""
