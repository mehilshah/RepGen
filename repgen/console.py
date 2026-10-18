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

# Chatty third-party loggers (per-request HTTP lines, SDK internals). They stay
# at WARNING even when RepGen itself runs at INFO, so ``-v`` shows RepGen's own
# progress instead of one line per API call. ``DEBUG`` unmutes them.
_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "openai",
    "anthropic",
    "google",
    "google_genai",
    "urllib3",
    "requests",
)


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

    _quiet_third_party(level)


def _quiet_third_party(level: str) -> None:
    """Pin noisy dependency loggers to WARNING unless we're debugging."""
    if str(level).upper() == "DEBUG":
        for name in _NOISY_LOGGERS:
            logging.getLogger(name).setLevel(logging.NOTSET)
        return
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


# Configure once at import with a conservative default.
configure_logging()
