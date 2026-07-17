from repgen.agent.context import ReadSnippet, RetrievedContext
from repgen.agent.generator import ReproductionGenerator

NET_SRC = (
    "class Net:\n"
    "    def __init__(self, num_classes, hidden=64):\n"
    "        self.num_classes = num_classes\n"
    "def train_step(model, data):\n"
    "    return model\n"
)

GOOD_CODE = (
    "```python\n"
    "from models.net import Net, train_step\n"
    "m = Net(10)\n"
    "r = train_step(m, [1, 2])\n"
    "assert r is not None\n"
    "```"
)

RESPONSES = {
    "failure signature": '{"exception_type":null,"message_substrings":["nan"],"trigger_apis":["train_step"]}',
    "step-by-step plan": '["Import Net", "Call train_step", "Assert"]',
    "reproduces this bug": GOOD_CODE,
    "reviewing whether": '{"reproduces": true, "reasoning":"ok", "issues": []}',
}


def _context():
    ctx = RetrievedContext(rationale="r", key_files=["models/net.py"])
    ctx.add_snippet(ReadSnippet("models/net.py", NET_SRC))
    return ctx


def test_generator_succeeds(scripted_backend):
    backend = scripted_backend(RESPONSES)
    gen = ReproductionGenerator(backend)
    result = gen.generate("Net train_step NaN", _context(), max_attempts=2)
    assert result.success is True
    assert "train_step" in result.code
    assert result.attempts[-1].result.passed


def test_generator_reports_failure_on_bad_code(scripted_backend):
    responses = dict(RESPONSES)
    responses["reproduces this bug"] = (
        "```python\nfrom models.net import Net, ghost\n```"
    )
    backend = scripted_backend(responses)
    gen = ReproductionGenerator(backend)
    result = gen.generate("Net train_step NaN", _context(), max_attempts=2)
    assert result.success is False
    # Best-effort code is still returned.
    assert result.code is not None
