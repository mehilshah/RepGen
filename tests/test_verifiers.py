import pytest

from repgen.agent.context import SymbolIndex
from repgen.agent.verifiers import (
    CompilationVerifier,
    FailureSignature,
    SymbolicVerifier,
    SyntaxVerifier,
    VerificationContext,
)

NET_SRC = (
    "class Net:\n"
    "    def __init__(self, num_classes, hidden=64):\n"
    "        self.num_classes = num_classes\n"
    "def train_step(model, data):\n"
    "    return model\n"
)


@pytest.fixture
def ctx():
    idx = SymbolIndex()
    idx.add_file("models/net.py", NET_SRC)
    return VerificationContext(
        refined_report="Net NaN",
        symbol_index=idx,
        failure_signature=FailureSignature(trigger_apis=["train_step"]),
    )


def test_syntax_fails_on_syntax_error(ctx):
    fb = SyntaxVerifier().verify("def (:", ctx)
    assert fb.passed is False
    assert "SyntaxError" in fb.findings[0].message


def test_syntax_passes_valid(ctx):
    assert SyntaxVerifier().verify("x = 1\n", ctx).passed


def test_compilation_detects_undefined(ctx):
    fb = CompilationVerifier().verify("print(undefined_name)\n", ctx)
    assert fb.passed is False


def test_symbolic_good_code_passes(ctx):
    code = (
        "from models.net import Net, train_step\n"
        "m = Net(10)\n"
        "r = train_step(m, [1, 2])\n"
        "assert r is not None\n"
    )
    fb = SymbolicVerifier().verify(code, ctx)
    assert fb.passed, fb.render()


def test_symbolic_unresolved_symbol(ctx):
    code = "from models.net import Net, missing_fn\nm = Net(10)\ntrain_step(m, 1)\n"
    fb = SymbolicVerifier().verify(code, ctx)
    assert fb.passed is False
    assert any("missing_fn" in f.message for f in fb.findings)


def test_symbolic_unexpected_kwarg(ctx):
    code = (
        "from models.net import Net, train_step\nNet(10, bogus=1)\ntrain_step(1, 2)\n"
    )
    fb = SymbolicVerifier().verify(code, ctx)
    assert any("bogus" in f.message for f in fb.findings)


def test_symbolic_missing_trigger_api_is_a_hint_not_a_block(ctx):
    # The reported failing behaviour is rarely a single named command, so an
    # absent trigger API must NOT fail the run — it only surfaces a soft hint.
    code = "from models.net import Net\nassert Net(10)\n"
    fb = SymbolicVerifier().verify(code, ctx)
    assert fb.passed is True
    assert fb.severity == "warning"
    assert any("buggy code path" in f.message for f in fb.findings)
    # And it must never prescribe "call API X" as a fix.
    assert all(f.suggestion is None for f in fb.findings)


def test_symbolic_trigger_api_via_attribute_counts_as_exercised(ctx):
    # ``train_step`` reached through an attribute reference (not a direct call)
    # still counts — the check looks at the whole referenced surface.
    code = "from models.net import Net\nobj = Net(10)\nfn = obj.train_step\n"
    fb = SymbolicVerifier().verify(code, ctx)
    assert not any("buggy code path" in f.message for f in fb.findings)


def test_symbolic_undefined_name(ctx):
    code = "from models.net import train_step\ntrain_step(ghost, 1)\n"
    fb = SymbolicVerifier().verify(code, ctx)
    assert any("ghost" in f.message for f in fb.findings)
