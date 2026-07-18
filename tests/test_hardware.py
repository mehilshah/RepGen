"""Tests for host hardware detection."""

from __future__ import annotations

from repgen.execution.hardware import HardwareInfo, detect_hardware


def test_detect_hardware_returns_sane_values():
    hw = detect_hardware()
    assert isinstance(hw, HardwareInfo)
    assert hw.cpu_count >= 1
    assert hw.python_version
    assert hw.total_ram_gb >= 0.0
    assert hw.free_disk_gb >= 0.0


def test_render_is_multiline_and_mentions_gpu():
    hw = detect_hardware()
    rendered = hw.render()
    assert "CPU:" in rendered
    assert "RAM:" in rendered
    assert "GPU:" in rendered


def test_has_gpu_matches_gpus_list():
    hw = HardwareInfo()
    assert hw.has_gpu is False
    hw2 = detect_hardware()
    assert hw2.has_gpu == bool(hw2.gpus)


def test_to_dict_roundtrips_fields():
    hw = detect_hardware()
    d = hw.to_dict()
    assert d["cpu_count"] == hw.cpu_count
    assert "gpus" in d
