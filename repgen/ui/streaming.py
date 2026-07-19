"""Live streaming renderer for LLM output.

Attached to a backend's ``on_stream`` callback, this shows a compact, live status
line while the model works, then leaves a concise one-line trace when the call
finishes. It is deliberately unobtrusive — no panels or dropdowns in the default
(silent) mode:

* **silent (default):** a single updating status line with a live token counter;
  on completion, one dim line with the real token counts.
* **verbose (``-v``):** the streaming text is also shown live (tail only) and a
  capped panel of the output is left in the scrollback.

Reasoning models rarely stream their raw thinking, so the token counter prefers
the provider's *real* usage (emitted as a ``usage`` event just before the call
ends) and only falls back to a char-based estimate while output is still in
flight — that's why the count is no longer a misleading ~0.

The live region is transient while active; nothing already on screen is erased.
On a non-interactive stream (no TTY) there is no live region — only the final
one-line trace is printed.
"""

from __future__ import annotations

import json
import sys

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from ..console import console

# Rough tokens≈chars/4 estimate for the *live* counter before the provider's
# exact usage arrives at the end of the call.
_CHARS_PER_TOKEN = 4
# Only keep a tail of the streamed text in the *live* region so redraws stay
# cheap while the model is producing output.
_MAX_TEXT_CHARS = 1600
# How many trailing lines of the answer to keep in the durable panel (verbose).
_PERSIST_MAX_LINES = 40


def _is_tty() -> bool:
    try:
        return bool(sys.stdout.isatty())
    except Exception:  # noqa: BLE001 - oddball streams count as non-TTY
        return False


class StreamRenderer:
    """Callable ``on_stream`` target that renders a compact live status line."""

    def __init__(self, label: str = "generating", verbose: bool = False) -> None:
        self.label = label
        self.verbose = verbose
        self._enabled = _is_tty()
        self._live = None
        self._text = ""
        self._reasoning_chars = 0
        self._usage: dict = {}

    # The backend calls this as (delta, kind).
    def __call__(self, delta: str, kind: str) -> None:
        if kind == "start":
            self._begin()
        elif kind == "end":
            self._finish()
        elif kind == "reasoning":
            self._reasoning_chars += len(delta)
            self._refresh()
        elif kind == "text":
            self._text += delta
            self._refresh()
        elif kind == "usage":
            self._record_usage(delta)
            self._refresh()

    # -- lifecycle --------------------------------------------------------
    def _begin(self) -> None:
        self._text = ""
        self._reasoning_chars = 0
        self._usage = {}
        if self._live is not None:
            self._finish()
        if not self._enabled:
            return
        from rich.live import Live

        self._live = Live(
            console=console,
            refresh_per_second=12,
            transient=True,
            vertical_overflow="crop",
        )
        try:
            self._live.start()
        except Exception:  # noqa: BLE001 - another Live may be active; degrade
            self._live = None
            self._enabled = False
            return
        self._refresh()

    def _finish(self) -> None:
        if self._live is not None:
            try:
                self._live.stop()
            finally:
                self._live = None
        self._persist()

    # -- usage / token counting ------------------------------------------
    def _record_usage(self, payload: str) -> None:
        try:
            data = json.loads(payload)
        except Exception:  # noqa: BLE001 - ignore a malformed usage blob
            return
        if isinstance(data, dict):
            self._usage = data

    def _reasoning_tokens(self) -> int:
        return self._reasoning_chars // _CHARS_PER_TOKEN

    def _output_tokens(self) -> int:
        return len(self._text) // _CHARS_PER_TOKEN

    def _token_summary(self) -> str:
        """Real counts from provider usage, or a ~estimate while streaming."""
        parts = []
        out = self._usage.get("output_tokens")
        if out is not None:
            parts.append(f"{out} output")
        else:
            parts.append(f"~{self._output_tokens()} output")
        reason = self._usage.get("reasoning_tokens")
        if reason is not None:
            parts.append(f"{reason} thinking")
        elif self._reasoning_chars:
            parts.append(f"~{self._reasoning_tokens()} thinking")
        return " · ".join(parts) + " tokens"

    # -- rendering --------------------------------------------------------
    def _render(self):
        state = self.label if self._text else "thinking…"
        header = Text(f"⟳ {state} · {self._token_summary()}", style="dim cyan")
        if self.verbose and self._text:
            body = Text(self._text[-_MAX_TEXT_CHARS:], style="white")
            return Group(header, Panel(body, border_style="cyan", padding=(0, 1)))
        return header

    def _refresh(self) -> None:
        if self._live is None:
            return
        try:
            self._live.update(self._render())
        except Exception:  # noqa: BLE001 - never let a render bug crash a run
            pass

    def _persist(self) -> None:
        """Leave a durable record: concise by default, a panel when verbose."""
        summary = self._token_summary()
        text = self._text.strip()
        if not self.verbose or not text:
            console.print(Text(f"✓ {self.label} · {summary}", style="dim cyan"))
            return
        lines = text.splitlines()
        hidden = 0
        if len(lines) > _PERSIST_MAX_LINES:
            hidden = len(lines) - _PERSIST_MAX_LINES
            lines = lines[-_PERSIST_MAX_LINES:]
        header_bits = [self.label, summary]
        if hidden:
            header_bits.append(f"+{hidden} earlier lines")
        console.print(
            Panel(
                Text("\n".join(lines), style="white"),
                title="[dim cyan]" + " · ".join(header_bits) + "[/dim cyan]",
                border_style="cyan",
                padding=(0, 1),
                expand=False,
            )
        )
