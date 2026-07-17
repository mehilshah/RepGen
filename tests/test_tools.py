from repgen.agent.tools import RepoToolbox


def test_list_dir(fixture_repo):
    tb = RepoToolbox(str(fixture_repo))
    out = tb.list_dir(".")
    assert "main.py" in out
    assert "models/" in out


def test_read_file_records_snippet_and_symbols(fixture_repo):
    tb = RepoToolbox(str(fixture_repo))
    tb.read_file("models/net.py")
    assert tb.context.snippets
    symbols = tb.context.symbol_index.all_symbols()
    assert "Net" in symbols
    assert "train_step" in symbols


def test_read_file_range(fixture_repo):
    tb = RepoToolbox(str(fixture_repo))
    out = tb.read_file("models/net.py", start=3, end=5)
    assert "class Net" in out


def test_find_definition(fixture_repo):
    tb = RepoToolbox(str(fixture_repo))
    out = tb.find_definition("train_step")
    assert "models/net.py" in out
    assert "def train_step" in out


def test_grep(fixture_repo):
    tb = RepoToolbox(str(fixture_repo))
    out = tb.grep(r"backward")
    assert "net.py" in out


def test_find_training_loops(fixture_repo):
    tb = RepoToolbox(str(fixture_repo))
    out = tb.find_training_loops()
    assert "models/net.py" in out


def test_search_code_bm25(fixture_repo):
    tb = RepoToolbox(str(fixture_repo))
    out = tb.search_code("training loss backward", 5)
    assert "net.py" in out
    assert "train_step" in out


def test_repo_map(fixture_repo):
    tb = RepoToolbox(str(fixture_repo))
    out = tb.repo_map()
    assert "class Net" in out
    assert "def train_step" in out


def test_repo_map_prefix(fixture_repo):
    tb = RepoToolbox(str(fixture_repo))
    out = tb.repo_map("models")
    assert "models/net.py" in out
    assert "main.py" not in out


def test_path_escape_rejected(fixture_repo):
    tb = RepoToolbox(str(fixture_repo))
    out = tb.dispatch("read_file", {"path": "../../etc/passwd"})
    assert "escapes" in out.lower()


def test_dispatch_unknown_tool(fixture_repo):
    tb = RepoToolbox(str(fixture_repo))
    assert "Unknown tool" in tb.dispatch("frobnicate", {})
