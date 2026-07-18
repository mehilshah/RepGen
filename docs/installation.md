# Installation

## Prerequisites

- **Python** 3.9 or higher
- **Git**

## Option A: pip (recommended)

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: .\venv\Scripts\activate

git clone https://github.com/mehilshah/RepGen
cd RepGen

# One lightweight install — no ML stack, no model downloads
pip install -e .
```

The install is intentionally small so the tool is fast to adopt. Retrieval is
LLM-driven over a pure-Python repo map + BM25 index, so there is no `torch` or
embedding-model dependency.

## Option B: Docker

The image installs the CLI and uses `repgen` as its entrypoint.

```bash
docker build -t repgen .
docker run --rm repgen backends
docker run --rm -e OPENAI_API_KEY repgen run \
  -b https://github.com/owner/repo/issues/123 \
  -r https://github.com/owner/repo.git --backend openai --yes
```

## Verify

```bash
repgen version
repgen backends
```
