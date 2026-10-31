"""Unit tests for AURA Loader widget."""
import pytest
pytest.importorskip("textual")
from aura.ui.widgets.loader import AURALoader, GRADIENT_PALETTE, SPINNER_FRAMES, WAVE_BLOCKS


def test_loader_init_and_frames():
    loader_grad = AURALoader(text="Thinking...", style="gradient")
    assert loader_grad.loader_style == "gradient"
    frame_grad = loader_grad._render_frame()
    assert "Thinking..." in frame_grad.plain

    loader_spin = AURALoader(text="Assessing", style="spinner")
    assert loader_spin.loader_style == "spinner"
    frame_spin = loader_spin._render_frame()
    assert "Assessing" in frame_spin.plain
    assert any(ch in frame_spin.plain for ch in SPINNER_FRAMES)

    loader_min = AURALoader(text="Executing", style="minimal")
    assert loader_min.loader_style == "minimal"
    frame_min = loader_min._render_frame()
    assert "Executing" in frame_min.plain


def test_loader_text_update():
    loader = AURALoader(text="Initial", style="spinner")
    loader.set_text("Updated state")
    assert loader.text_label == "Updated state"
    assert "Updated state" in loader._render_frame().plain


def test_realistic_animation_styles():
    # 1. Neural Wave
    loader_wave = AURALoader(text="Synthesizing plan", style="neural_wave")
    loader_wave._frame = 5
    frame_wave = loader_wave._render_frame()
    assert "Synthesizing plan" in frame_wave.plain
    assert any(b in frame_wave.plain for b in WAVE_BLOCKS)

    # 2. Matrix Decode
    loader_matrix = AURALoader(text="Security scan", style="matrix_decode")
    loader_matrix._frame = 3
    frame_matrix = loader_matrix._render_frame()
    assert "0x" in frame_matrix.plain

    # 3. Gaussian Shimmer
    loader_shimmer = AURALoader(text="JEV Policy Evaluation", style="shimmer")
    loader_shimmer._frame = 8
    frame_shimmer = loader_shimmer._render_frame()
    assert "JEV Policy Evaluation" in frame_shimmer.plain

    # 4. Telemetry Pulse
    loader_pulse = AURALoader(text="Querying database", style="pulse")
    loader_pulse._frame = 12
    frame_pulse = loader_pulse._render_frame()
    assert "Querying database" in frame_pulse.plain
    assert any(ch in frame_pulse.plain for ch in ["─", "╱", "▲", "▼", "╲"])


def test_adaptive_stage_transitions():
    loader = AURALoader(text="Initial", style="spinner")
    
    # Auto stage detection from keywords
    loader.set_text("Intercepting gateway call")
    assert loader.loader_style == "matrix_decode"

    loader.set_text("JEV assessing risk")
    assert loader.loader_style == "shimmer"

    loader.set_text("Executing SQL query")
    assert loader.loader_style == "pulse"

    loader.set_text("Thinking of plan")
    assert loader.loader_style == "neural_wave"

