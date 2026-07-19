"""Rich terminal UI for RepGen's execution engine.

Provides a Claude-Code-style presentation layer over the execution pipeline's
progress events: milestone-first progress, dependency-install status, detailed
output logged to a file (shown inline only with ``-v``), clear error/verdict
visualization, command visibility, and a final summary — plus an interactive
confirmation prompt for the Medium/Large complexity gates.
"""

from __future__ import annotations

from .execution_view import ExecutionReporter, interactive_confirm
from .streaming import StreamRenderer

__all__ = ["ExecutionReporter", "interactive_confirm", "StreamRenderer"]
