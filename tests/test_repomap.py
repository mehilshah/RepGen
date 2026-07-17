from repgen.agent.repomap import BM25, RepoMap, tokenize


def test_bm25_ranks_relevant_doc_first():
    corpus = [
        tokenize("train the model with backward and optimizer step"),
        tokenize("parse configuration from a yaml file"),
        tokenize("render the html template for the page"),
    ]
    bm25 = BM25(corpus)
    ranked = bm25.rank(tokenize("model backward optimizer"), top_k=3)
    assert ranked, "expected at least one hit"
    assert ranked[0][0] == 0
    assert ranked[0][1] > 0


def test_bm25_empty_query_returns_nothing():
    bm25 = BM25([tokenize("hello world")])
    assert bm25.rank(tokenize("nonexistent term"), top_k=5) == []


def test_repomap_outline_and_search(fixture_repo):
    rm = RepoMap(str(fixture_repo)).build()
    rendered = rm.render()
    assert "class Net" in rendered
    assert "def train_step" in rendered

    outline = rm.outline("models/net.py")
    assert outline and "Net" in outline

    results = rm.search("training loop backward loss", top_k=3)
    assert results
    top_chunk, score = results[0]
    assert top_chunk.path == "models/net.py"
    assert score > 0


def test_repomap_handles_syntax_errors(tmp_path):
    (tmp_path / "broken.py").write_text("def (:\n")
    (tmp_path / "ok.py").write_text("def good():\n    return 1\n")
    rm = RepoMap(str(tmp_path)).build()
    # Broken file is skipped; the valid one is still mapped.
    assert "def good" in rm.render()
