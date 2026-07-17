from repgen.agent.explorer import ExplorationAgent, parse_action
from repgen.agent.tools import RepoToolbox
from repgen.backends.base import LLMBackend, LLMResponse


def test_parse_action_plain_json():
    a = parse_action('{"thought":"t","tool":"list_dir","args":{"path":"."}}')
    assert a["tool"] == "list_dir"


def test_parse_action_fenced():
    a = parse_action('sure:\n```json\n{"tool":"finish","args":{}}\n```')
    assert a["tool"] == "finish"


def test_parse_action_embedded():
    a = parse_action('Thought... {"tool":"grep","args":{"pattern":"x"}} done')
    assert a["tool"] == "grep"


def test_parse_action_invalid_returns_none():
    assert parse_action("no json here") is None


class SequenceBackend(LLMBackend):
    name = "seq"

    def __init__(self, actions):
        super().__init__("seq-1")
        self.actions = actions
        self.i = 0

    def generate(self, prompt, **kwargs):
        act = self.actions[min(self.i, len(self.actions) - 1)]
        self.i += 1
        return LLMResponse(text=act)


def test_explore_collects_context_and_symbols(fixture_repo):
    backend = SequenceBackend(
        [
            '{"thought":"read","tool":"read_file","args":{"path":"models/net.py"}}',
            '{"thought":"done","tool":"finish","args":{"rationale":"found","files":["models/net.py"]}}',
        ]
    )
    agent = ExplorationAgent(backend, RepoToolbox(str(fixture_repo)), max_steps=5)
    ctx = agent.explore("Net train_step NaN")
    assert ctx.key_files == ["models/net.py"]
    assert "Net" in ctx.symbol_index.all_symbols()
    assert ctx.rationale == "found"


def test_explore_handles_unparseable_then_finishes(fixture_repo):
    backend = SequenceBackend(
        ["garbage", '{"tool":"finish","args":{"rationale":"ok","files":[]}}']
    )
    agent = ExplorationAgent(backend, RepoToolbox(str(fixture_repo)), max_steps=5)
    ctx = agent.explore("bug")
    assert ctx.rationale == "ok"
