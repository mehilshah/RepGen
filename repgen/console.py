"""Shared Rich console and logging configuration for RepGen."""

import logging

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

custom_theme = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "bold green",
        "highlight": "magenta",
        "code": "bold white on black",
    }
)

console = Console(theme=custom_theme)

_LOGGING_CONFIGURED = False


def configure_logging(level: str = "WARNING") -> None:
    """Configure the root logger to render through the shared Rich console.

    Kept quiet by default so the interactive CLI stays clean; raise the level
    (e.g. ``INFO``/``DEBUG``) for troubleshooting.
    """
    global _LOGGING_CONFIGURED
    if not _LOGGING_CONFIGURED:
        logging.basicConfig(
            level=level,
            format="%(message)s",
            datefmt="[%X]",
            handlers=[RichHandler(console=console, rich_tracebacks=True, markup=True)],
        )
        _LOGGING_CONFIGURED = True
    else:
        logging.getLogger().setLevel(level)


# Configure once at import with a conservative default.
configure_logging()
