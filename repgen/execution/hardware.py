"""Host hardware detection for the execution planner.

Kept dependency-light in the spirit of the rest of RepGen: everything here is
best-effort over the standard library (``os``, ``shutil``, ``platform``,
``subprocess``) with graceful fallbacks. If the optional :mod:`psutil` package
is importable we use it for more accurate memory numbers, but it is never
required.

The resulting :class:`HardwareInfo` feeds :class:`repgen.execution.planner`,
which asks the LLM to reason about how heavy an execution will be relative to
the machine it will run on.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from typing import List, Optional

logger = logging.getLogger("repgen.execution.hardware")


@dataclass
class GPUInfo:
    """A single detected GPU (best effort, via ``nvidia-smi``)."""

    name: str
    memory_mb: Optional[int] = None

    def render(self) -> str:
        if self.memory_mb:
            return f"{self.name} ({self.memory_mb / 1024:.0f} GB)"
        return self.name


@dataclass
class HardwareInfo:
    """A snapshot of the host's compute resources."""

    os: str = ""
    arch: str = ""
    python_version: str = ""
    cpu_count: int = 1
    cpu_model: str = ""
    total_ram_gb: float = 0.0
    available_ram_gb: float = 0.0
    free_disk_gb: float = 0.0
    gpus: List[GPUInfo] = field(default_factory=list)

    @property
    def has_gpu(self) -> bool:
        return bool(self.gpus)

    def render(self) -> str:
        """A compact single-block human/LLM-facing summary."""
        lines = [
            f"OS: {self.os} ({self.arch})",
            f"Python: {self.python_version}",
            f"CPU: {self.cpu_count} core(s)"
            + (f" — {self.cpu_model}" if self.cpu_model else ""),
            f"RAM: {self.available_ram_gb:.1f} GB free / {self.total_ram_gb:.1f} GB total",
            f"Disk: {self.free_disk_gb:.1f} GB free",
        ]
        if self.gpus:
            lines.append("GPU: " + "; ".join(g.render() for g in self.gpus))
        else:
            lines.append("GPU: none detected")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return asdict(self)


def _cpu_model() -> str:
    """Best-effort CPU model string across platforms."""
    system = platform.system()
    try:
        if system == "Linux" and os.path.exists("/proc/cpuinfo"):
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
        elif system == "Darwin":
            out = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if out.returncode == 0:
                return out.stdout.strip()
    except Exception as e:  # noqa: BLE001 - detection is best effort
        logger.debug("CPU model detection failed: %s", e)
    return platform.processor() or ""


def _memory_gb() -> tuple[float, float]:
    """Return ``(total_gb, available_gb)`` best effort."""
    # Prefer psutil when available for accurate "available" memory.
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        return vm.total / 1024**3, vm.available / 1024**3
    except Exception:  # noqa: BLE001 - psutil optional
        pass

    # Linux: parse /proc/meminfo.
    try:
        if os.path.exists("/proc/meminfo"):
            info = {}
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    key, _, rest = line.partition(":")
                    info[key.strip()] = rest.strip()
            total_kb = int(info.get("MemTotal", "0 kB").split()[0])
            avail_kb = int(
                info.get("MemAvailable", info.get("MemFree", "0 kB")).split()[0]
            )
            return total_kb / 1024**2, avail_kb / 1024**2
    except Exception as e:  # noqa: BLE001
        logger.debug("meminfo parse failed: %s", e)

    # Generic fallback via sysconf (total only; assume all available).
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        phys_pages = os.sysconf("SC_PHYS_PAGES")
        total = page_size * phys_pages / 1024**3
        return total, total
    except (ValueError, AttributeError, OSError):
        return 0.0, 0.0


def _free_disk_gb(path: Optional[str] = None) -> float:
    try:
        usage = shutil.disk_usage(path or os.getcwd())
        return usage.free / 1024**3
    except Exception as e:  # noqa: BLE001
        logger.debug("disk usage failed: %s", e)
        return 0.0


def _detect_gpus() -> List[GPUInfo]:
    """Detect NVIDIA GPUs via ``nvidia-smi`` (no hard dependency)."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return []
    try:
        out = subprocess.run(
            [
                smi,
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode != 0:
            return []
        gpus: List[GPUInfo] = []
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if not parts or not parts[0]:
                continue
            mem: Optional[int] = None
            if len(parts) > 1:
                try:
                    mem = int(float(parts[1]))
                except ValueError:
                    mem = None
            gpus.append(GPUInfo(name=parts[0], memory_mb=mem))
        return gpus
    except Exception as e:  # noqa: BLE001
        logger.debug("nvidia-smi query failed: %s", e)
        return []


def detect_hardware(disk_path: Optional[str] = None) -> HardwareInfo:
    """Detect host hardware, returning a :class:`HardwareInfo`.

    ``disk_path`` selects which filesystem to report free space for (defaults to
    the current working directory, where the venv/run artifacts land).
    """
    total_ram, avail_ram = _memory_gb()
    info = HardwareInfo(
        os=f"{platform.system()} {platform.release()}".strip(),
        arch=platform.machine(),
        python_version=platform.python_version(),
        cpu_count=os.cpu_count() or 1,
        cpu_model=_cpu_model(),
        total_ram_gb=round(total_ram, 2),
        available_ram_gb=round(avail_ram, 2),
        free_disk_gb=round(_free_disk_gb(disk_path), 2),
        gpus=_detect_gpus(),
    )
    logger.debug("Detected hardware: %s", info.render().replace("\n", " | "))
    return info
