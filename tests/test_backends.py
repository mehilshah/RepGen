import pytest

from repgen.backends import BACKEND_NAMES, get_backend, list_backends
from repgen.backends.openai_backend import OllamaBackend, OpenAIBackend


class _CapturingCompletions:
    def __init__(self):
        self.params = None

    def create(self, **params):
        from types import SimpleNamespace

        self.params = params
        message = SimpleNamespace(content="ok")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)], usage=None
        )


def test_registry_has_five_backends():
    assert set(BACKEND_NAMES) == {
        "openai",
        "claude",
        "gemini",
        "openrouter",
        "ollama",
    }


def test_get_backend_unknown_raises():
    with pytest.raises(ValueError):
        get_backend("nope")


def test_get_backend_applies_model():
    b = get_backend("openai", model="gpt-4o-mini")
    assert b.model == "gpt-4o-mini"


def test_default_model_used_when_unspecified():
    b = get_backend("claude")
    assert b.model == b.default_model


def test_api_key_backend_not_configured(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert get_backend("openai").is_configured() is False


def test_api_key_backend_configured_via_arg():
    assert get_backend("openai", api_key="sk-test").is_configured() is True


def test_ollama_is_keyless_and_configured():
    b = get_backend("ollama")
    assert b.env_key is None
    assert b.is_configured() is True


def test_ollama_base_url_respects_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://remote:1234")
    assert OllamaBackend().base_url == "http://remote:1234/v1"
    monkeypatch.setenv("OLLAMA_HOST", "http://remote:1234/v1")
    assert OllamaBackend().base_url == "http://remote:1234/v1"


def test_list_backends_returns_all():
    assert len(list_backends()) == len(BACKEND_NAMES)


def test_openai_reasoning_model_uses_valid_params_without_400_retry(monkeypatch):
    from types import SimpleNamespace

    completions = _CapturingCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    backend = OpenAIBackend(model="gpt-5-mini", api_key="k")
    monkeypatch.setattr(backend, "_client", lambda: client)

    assert backend.generate("prompt").text == "ok"
    assert completions.params["max_completion_tokens"] > 0
    assert "max_tokens" not in completions.params
    assert "temperature" not in completions.params


def test_latest_openai_reasoning_model_uses_valid_params(monkeypatch):
    from types import SimpleNamespace

    completions = _CapturingCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    backend = OpenAIBackend(model="gpt-6-astra", api_key="k")
    monkeypatch.setattr(backend, "_client", lambda: client)

    assert backend.generate("prompt").text == "ok"
    assert "max_completion_tokens" in completions.params
    assert "max_tokens" not in completions.params
    assert "temperature" not in completions.params
