"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from repgen.backends.base import LLMBackend, LLMResponse

FIXTURE_FILES = {
    "models/net.py": (
        "import torch\n\n"
        "class Net:\n"
        "    def __init__(self, num_classes, hidden=64):\n"
        "        self.num_classes = num_classes\n\n"
        "def train_step(model, data):\n"
        "    for epoch in range(3):\n"
        "        loss = model.forward(data)\n"
        "        loss.backward()\n"
        "    return loss\n"
    ),
    "main.py": "from models.net import Net, train_step\nn = Net(10)\n",
}


@pytest.fixture
def fixture_repo(tmp_path):
    for rel, content in FIXTURE_FILES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return tmp_path


class ScriptedBackend(LLMBackend):
    """A deterministic backend that maps prompt keywords to canned responses."""

    name = "scripted"
    default_model = "scripted-1"

    def __init__(self, responses=None):
        super().__init__("scripted-1")
        self.responses = responses or {}
        self.calls = []

    def generate(self, prompt, **kwargs) -> LLMResponse:
        self.calls.append(prompt)
        for key, value in self.responses.items():
            if key in prompt.lower():
                text = value(prompt) if callable(value) else value
                return LLMResponse(text=text)
        return LLMResponse(text="")


@pytest.fixture
def scripted_backend():
    return ScriptedBackend
