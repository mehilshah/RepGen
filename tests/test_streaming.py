"""Streaming: SSE parsers, the live renderer, and the OpenAI stream path."""

from __future__ import annotations

import json
from types import SimpleNamespace

from repgen.backends.claude import parse_claude_sse_event
from repgen.backends.gemini import parse_gemini_sse_chunk
from repgen.backends.openai_backend import OpenAIBackend
from repgen.ui.streaming import StreamRenderer


# -- Claude SSE ----------------------------------------------------------
def test_claude_sse_text_and_thinking():
    assert parse_claude_sse_event(
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hi"}}
    ) == ("hi", "", {})
    assert parse_claude_sse_event(
        {"type": "content_block_delta",
         "delta": {"type": "thinking_delta", "thinking": "hmm"}}
    ) == ("", "hmm", {})


def test_claude_sse_usage_events():
    _, _, u1 = parse_claude_sse_event(
        {"type": "message_start", "message": {"usage": {"input_tokens": 5}}}
    )
    _, _, u2 = parse_claude_sse_event(
        {"type": "message_delta", "usage": {"output_tokens": 9}}
    )
    assert u1 == {"input_tokens": 5}
    assert u2 == {"output_tokens": 9}
    # Unknown events are inert.
    assert parse_claude_sse_event({"type": "ping"}) == ("", "", {})


# -- Gemini SSE ----------------------------------------------------------
def test_gemini_sse_splits_thought_from_text():
    chunk = {
        "candidates": [
            {"content": {"parts": [
                {"text": "thinking bit", "thought": True},
                {"text": "answer bit"},
            ]}}
        ],
        "usageMetadata": {"totalTokenCount": 12},
    }
    text, reasoning, usage = parse_gemini_sse_chunk(chunk)
    assert text == "answer bit"
    assert reasoning == "thinking bit"
    assert usage == {"totalTokenCount": 12}


def test_gemini_sse_empty_chunk():
    assert parse_gemini_sse_chunk({}) == ("", "", {})


# -- Renderer ------------------------------------------------------------
def test_stream_renderer_lifecycle_and_token_estimate():
    r = StreamRenderer()
    r("", "start")
    r("x" * 40, "reasoning")   # 40 chars ≈ 10 tokens
    r("import x\n", "text")
    assert r._reasoning_tokens() == 10
    assert "import x" in r._text
    r("", "end")               # must not raise; Live torn down
    assert r._live is None


def test_stream_renderer_survives_end_without_start():
    r = StreamRenderer()
    r("", "end")  # no active Live — should be a no-op, not a crash
    assert r._live is None


# -- OpenAI streaming path ----------------------------------------------
def _chunk(content=None, reasoning=None, usage=None):
    choices = []
    if content is not None or reasoning is not None:
        delta = SimpleNamespace(content=content, reasoning=reasoning,
                                reasoning_content=None)
        choices = [SimpleNamespace(delta=delta)]
    return SimpleNamespace(choices=choices, usage=usage)


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __iter__(self):
        return iter(self._chunks)


class _FakeClient:
    def __init__(self, chunks):
        create = lambda **kw: _FakeStream(chunks)  # noqa: E731
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def test_openai_stream_collects_text_and_emits_deltas(monkeypatch):
    usage = SimpleNamespace(
        prompt_tokens=3, completion_tokens=7, total_tokens=10,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=4),
    )
    chunks = [
        _chunk(reasoning="think "),
        _chunk(content="hello "),
        _chunk(content="world"),
        _chunk(usage=usage),
    ]
    backend = OpenAIBackend(model="gpt-5-mini", api_key="k")
    monkeypatch.setattr(backend, "_client", lambda: _FakeClient(chunks))

    events: list[tuple[str, str]] = []
    backend.on_stream = lambda d, k: events.append((d, k))

    resp = backend.generate("prompt")

    assert resp.text == "hello world"
    assert resp.usage["reasoning_tokens"] == 4
    assert ("", "start") == events[0]
    assert ("", "end") == events[-1]
    assert ("hello ", "text") in events
    assert ("think ", "reasoning") in events
    # A usage event is emitted just before end, carrying normalized token counts.
    usage_events = [d for d, k in events if k == "usage"]
    assert usage_events, "expected a usage event"
    normalized = json.loads(usage_events[-1])
    assert normalized["output_tokens"] == 7
    assert normalized["reasoning_tokens"] == 4
    assert events[-2] == (usage_events[-1], "usage")  # right before "end"


# -- Usage normalization + token counter --------------------------------
def test_normalize_usage_across_providers():
    from repgen.backends.base import normalize_usage

    # OpenAI
    assert normalize_usage(
        {"prompt_tokens": 3, "completion_tokens": 7, "reasoning_tokens": 4}
    ) == {"input_tokens": 3, "output_tokens": 7, "reasoning_tokens": 4}
    # Gemini
    assert normalize_usage(
        {"promptTokenCount": 10, "candidatesTokenCount": 200,
         "thoughtsTokenCount": 88, "totalTokenCount": 298}
    ) == {"input_tokens": 10, "output_tokens": 200,
          "reasoning_tokens": 88, "total_tokens": 298}
    # Claude (thinking folded into output; no separate reasoning count)
    assert normalize_usage({"input_tokens": 5, "output_tokens": 320}) == {
        "input_tokens": 5,
        "output_tokens": 320,
    }
    assert normalize_usage({}) == {}


def test_stream_renderer_usage_event_shows_real_tokens():
    # Reasoning models don't stream thinking, so the char estimate is ~0 — the
    # real counts must come from the usage event, not the stream.
    r = StreamRenderer()
    r._enabled = False  # no live region in the test harness
    r("", "start")
    r("def f(): pass\n", "text")
    assert "~" in r._token_summary()  # estimate before usage arrives
    r(json.dumps({"output_tokens": 512, "reasoning_tokens": 448}), "usage")
    summary = r._token_summary()
    assert "512 output" in summary
    assert "448 thinking" in summary
    assert "~" not in summary  # now exact, not an estimate
    r("", "end")


def test_stream_renderer_ignores_malformed_usage():
    r = StreamRenderer()
    r._enabled = False
    r("", "start")
    r("not-json", "usage")  # must not raise
    r("", "end")
