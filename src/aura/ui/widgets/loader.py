"""AURA realistic animated loader widget.

Features realistic physical & visual animations:
1. Neural Wave (neural_wave / wave): Dynamic dual-harmonic frequency spectrum with color lerp.
2. Sci-Fi Decryptor (matrix_decode / matrix): Scrambled memory inspection with character resolution.
3. Gaussian Shimmer (shimmer / gradient): Realistic light-beam sweep with Gaussian illumination falloff.
4. Telemetry Pulse (pulse / ecg): Sinusoidal cardiac telemetry waveform with millisecond jitter.
5. Braille Spinner (spinner): Classic precision high-speed mechanical spinner.
6. Minimal Dot Progression (minimal): Elegant minimalist dot progression.

Also features real-time elapsed timer tracking and automatic pipeline-stage adaptation.
"""
from __future__ import annotations
import math
import random
import time
from typing import Optional
from textual.widgets import Static
from rich.text import Text

# Smooth Unicode height blocks for audio / neural wave
WAVE_BLOCKS = [" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

# Classic Braille spinner frames
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# Cyberpunk glyphs for matrix decode
DECRYPT_GLYPHS = "0123456789ABCDEF!@#%&*<>§ΔΞΨλφ"

# Electric cyber palette for wave gradient
GRADIENT_PALETTE = [
    "#00e5ff",  # bright cyan
    "#38bdf8",  # sky blue
    "#60a5fa",  # light blue
    "#818cf8",  # indigo
    "#a855f7",  # purple
    "#c084fc",  # lavender
    "#e879f9",  # fuchsia
    "#f43f5e",  # rose / neon pink
    "#e879f9",
    "#c084fc",
    "#a855f7",
    "#818cf8",
    "#60a5fa",
    "#38bdf8",
]


class AURALoader(Static):
    """Realistic animated status indicator showing agent reasoning, security checks, and tool calls."""

    DEFAULT_CSS = """
    AURALoader {
        height: 1;
        background: transparent;
        padding: 0 1;
        margin: 0;
        display: none;
    }
    AURALoader.active {
        display: block;
    }
    """

    def __init__(
        self,
        text: str = "Thinking...",
        style: str = "neural_wave",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.text_label = text
        self.loader_style = style if style in (
            "neural_wave", "wave", "matrix_decode", "matrix",
            "shimmer", "gradient", "pulse", "ecg", "spinner", "minimal"
        ) else "neural_wave"
        self._frame = 0
        self._timer = None
        self._active = False
        self._start_time = 0.0
        self._lock_index = 0
        self._auto_stage = True

    def start(self, text: Optional[str] = None, stage: Optional[str] = None) -> None:
        """Start the animation loop and reset the elapsed timer."""
        if text:
            self.text_label = text
        self._frame = 0
        self._lock_index = 0
        self._start_time = time.monotonic()
        self._active = True
        self.add_class("active")

        if stage:
            self._set_stage_style(stage)

        interval = 0.07 if self.loader_style in ("neural_wave", "wave", "pulse", "ecg") else (
            0.08 if self.loader_style in ("matrix_decode", "matrix") else 0.10
        )
        if self._timer is None:
            self._timer = self.set_interval(interval, self._tick)
        self.refresh()

    def set_text(self, text: str, stage: Optional[str] = None) -> None:
        """Update display text and adaptively transition animation stage if detected."""
        self.text_label = text
        if stage:
            self._set_stage_style(stage)
        elif self._auto_stage:
            t_low = text.lower()
            if "intercept" in t_low or "gateway" in t_low:
                self._set_stage_style("intercepting")
            elif "jev" in t_low or "assess" in t_low or "evaluat" in t_low or "polic" in t_low:
                self._set_stage_style("assessing")
            elif "execut" in t_low or "quer" in t_low:
                self._set_stage_style("executing")
            elif "think" in t_low or "plan" in t_low:
                self._set_stage_style("thinking")
        self.refresh()

    def _set_stage_style(self, stage: str) -> None:
        st = stage.lower()
        if st in ("thinking", "planning"):
            self.loader_style = "neural_wave"
        elif st in ("intercepting", "gateway"):
            self.loader_style = "matrix_decode"
            self._lock_index = 0
        elif st in ("assessing", "jev", "policy"):
            self.loader_style = "shimmer"
        elif st in ("executing", "running", "querying"):
            self.loader_style = "pulse"

    def stop(self) -> None:
        """Stop animation and clear loader display."""
        self._active = False
        self.remove_class("active")
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.update("")
        self.refresh()

    def _tick(self) -> None:
        if not self._active:
            return
        self._frame += 1
        self.update(self._render_frame())

    def _get_elapsed_badge(self) -> str:
        """Return formatted elapsed time badge [1.2s]."""
        elapsed = time.monotonic() - self._start_time if self._start_time > 0 else 0.0
        return f"[{elapsed:.1f}s]"

    def _render_frame(self) -> Text:
        t = Text()
        style = self.loader_style
        elapsed_badge = self._get_elapsed_badge()

        # 1. Neural Frequency Wave (Realistic fluid dual-harmonic waveform)
        if style in ("neural_wave", "wave"):
            t.append("  ", style="")
            t_sec = self._frame * 0.28
            wave_len = 8
            for x in range(wave_len):
                # Dual harmonic sine wave: fundamental + 2nd harmonic
                val = 0.5 + 0.35 * math.sin(x * 0.85 - t_sec * 2.2) + 0.15 * math.sin(x * 1.7 + t_sec * 1.1)
                idx = max(0, min(len(WAVE_BLOCKS) - 1, int(val * len(WAVE_BLOCKS))))
                color_idx = int((val) * (len(GRADIENT_PALETTE) - 1))
                color = GRADIENT_PALETTE[color_idx]
                t.append(WAVE_BLOCKS[idx], style=f"bold {color}")
            t.append("  ", style="")
            t.append(f"{self.text_label} ", style="bold #e2e8f0")
            t.append(elapsed_badge, style="dim #00e5ff")

        # 2. Cyberpunk Matrix Decryptor (Memory address + character resolution)
        elif style in ("matrix_decode", "matrix"):
            hex_addr = f"0x{0x7F20 + ((self._frame * 8) % 0x0100):04X}"
            t.append(f"  [{hex_addr}] ", style="dim #00e5ff")
            full_text = self.text_label
            # Incrementally lock characters into place
            if self._frame % 2 == 0 and self._lock_index < len(full_text):
                self._lock_index += 1

            locked = full_text[:self._lock_index]
            scramble_len = min(5, len(full_text) - self._lock_index)
            scrambled = "".join(random.choice(DECRYPT_GLYPHS) for _ in range(scramble_len))
            remainder = full_text[self._lock_index + scramble_len:]

            t.append(locked, style="bold #10b981")
            if scrambled:
                t.append(scrambled, style="bold #00e5ff on #0c1a2e")
            t.append(remainder, style="dim #64748b")
            t.append(f" {elapsed_badge}", style="dim #c084fc")

        # 3. Gaussian Light-Beam Shimmer (Realistic Gaussian light sweeping across text)
        elif style in ("shimmer", "gradient"):
            t.append("  ◈ ", style="bold #00e5ff")
            full_text = self.text_label
            text_len = len(full_text)
            center = (self._frame * 1.5) % (text_len + 12) - 4

            for i, ch in enumerate(full_text):
                dist = abs(i - center)
                if dist <= 1.2:
                    t.append(ch, style="bold #ffffff on #083344")
                elif dist <= 3.2:
                    t.append(ch, style="bold #00e5ff")
                elif dist <= 6.0:
                    t.append(ch, style="#c084fc")
                else:
                    t.append(ch, style="dim #475569")
            t.append(f"  {elapsed_badge}", style="dim #38bdf8")

        # 4. Cardiac ECG Telemetry Pulse
        elif style in ("pulse", "ecg"):
            pulse_pattern = "────────/\\_─/\\──────────"
            offset = (self._frame * 2) % len(pulse_pattern)
            visual = (pulse_pattern + pulse_pattern)[offset:offset+14]
            t.append("  [PULSE] ", style="bold #10b981")
            t.append(visual, style="bold #00e5ff")
            t.append(f"  {self.text_label} ", style="bold #e2e8f0")
            t.append(elapsed_badge, style="dim #f59e0b")

        # 5. Braille Mechanical Spinner
        elif style == "spinner":
            char = SPINNER_FRAMES[self._frame % len(SPINNER_FRAMES)]
            t.append("  ", style="")
            t.append(char, style="bold #00e5ff")
            t.append(f"  {self.text_label} ", style="#e2e8f0")
            t.append(elapsed_badge, style="dim #64748b")

        # 6. Minimalist Dot Progression
        else:
            dots = [".", "..", "...", "...."]
            dot_str = dots[self._frame % len(dots)]
            t.append("  ", style="")
            t.append(f"{self.text_label}{dot_str:<4} ", style="dim #00e5ff")
            t.append(elapsed_badge, style="dim #475569")

        return t
