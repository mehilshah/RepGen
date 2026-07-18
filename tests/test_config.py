import pytest

from repgen.config import RepGenConfig


def test_roundtrip(tmp_path):
    path = tmp_path / "config.toml"
    cfg = RepGenConfig(backend="claude", model="claude-sonnet-4-5", max_attempts=5)
    cfg.save(path)
    loaded = RepGenConfig.load(path)
    assert loaded.backend == "claude"
    assert loaded.model == "claude-sonnet-4-5"
    assert loaded.max_attempts == 5


def test_load_missing_returns_defaults(tmp_path):
    cfg = RepGenConfig.load(tmp_path / "absent.toml")
    assert cfg.backend == "openai"


def test_set_coerces_int():
    cfg = RepGenConfig()
    cfg.set("max_explore_steps", "20")
    assert cfg.max_explore_steps == 20


def test_set_unknown_key_raises():
    with pytest.raises(KeyError):
        RepGenConfig().set("bogus", "x")


def test_to_dict_omits_none():
    cfg = RepGenConfig(model=None)
    assert "model" not in cfg.to_dict()
