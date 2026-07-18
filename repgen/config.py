"""User configuration for RepGen, persisted as TOML.

Resolution order (highest priority first):
    1. Explicit CLI flags
    2. Values in ``~/.config/repgen/config.toml`` (or ``$REPGEN_CONFIG``)
    3. Built-in defaults below
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - <3.11 fallback
    import tomli as tomllib  # type: ignore

DEFAULT_BACKEND = "openai"
DEFAULT_OUTPUT_DIR = "./repgen_results"
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_EXPLORE_STEPS = 12


def config_path() -> Path:
    """Location of the config file (override with ``$REPGEN_CONFIG``)."""
    override = os.getenv("REPGEN_CONFIG")
    if override:
        return Path(override).expanduser()
    base = os.getenv("XDG_CONFIG_HOME", "~/.config")
    return Path(base).expanduser() / "repgen" / "config.toml"


@dataclass
class RepGenConfig:
    backend: str = DEFAULT_BACKEND
    model: Optional[str] = None
    output_dir: str = DEFAULT_OUTPUT_DIR
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    max_explore_steps: int = DEFAULT_MAX_EXPLORE_STEPS

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "RepGenConfig":
        path = path or config_path()
        if not path.exists():
            return cls()
        with open(path, "rb") as f:
            data = tomllib.load(f)
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def save(self, path: Optional[Path] = None) -> Path:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._dumps())
        return path

    def _dumps(self) -> str:
        """Serialize to TOML without a third-party writer dependency."""
        lines = ["# RepGen configuration", ""]
        for key, value in self.to_dict().items():
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif isinstance(value, (int, float)):
                rendered = str(value)
            else:
                rendered = '"' + str(value).replace('"', '\\"') + '"'
            lines.append(f"{key} = {rendered}")
        return "\n".join(lines) + "\n"

    def set(self, key: str, value: str) -> None:
        """Set a field from a string value, coercing to the field's type."""
        if key not in self.__dataclass_fields__:
            raise KeyError(
                f"Unknown config key '{key}'. Valid keys: "
                f"{', '.join(self.__dataclass_fields__)}"
            )
        if key in {"max_attempts", "max_explore_steps"}:
            setattr(self, key, int(value))
        else:
            setattr(self, key, value)
