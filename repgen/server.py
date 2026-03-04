import os
import re
import uuid
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.staticfiles import StaticFiles

from .core import RepGenService
from .utils import query_llm


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Preloading models...")
    from .retrieval.config import Config
    from .retrieval.models.hybrid_search import HybridSearchIndex

    config = Config(
        repo_path=".", bug_report_path="requirements.txt", output_dir="./repgen_results"
    )
    _ = HybridSearchIndex(
        embedding_model=config.EMBEDDING_MODEL,
        reranker_model=config.RERANKER_MODEL,
        config=None,
    )
    print("Models preloaded successfully.")
    yield


app = FastAPI(title="RepGen API", lifespan=lifespan)

DEFAULT_CONNECT_SRC = ["'self'", "https://api.github.com", "https://github.com"]
EXTRA_CONNECT_SRC = os.getenv("REPGEN_CSP_CONNECT_SRC_EXTRA", "").split(",")
CONNECT_SRC = " ".join(
    [*DEFAULT_CONNECT_SRC, *[src.strip() for src in EXTRA_CONNECT_SRC if src.strip()]]
)

CSP_POLICY = "; ".join(
    [
        "default-src 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "img-src 'self' data:",
        "script-src 'self'",
        "style-src 'self'",
        f"connect-src {CONNECT_SRC}",
        "font-src 'self' data:",
        "upgrade-insecure-requests",
    ]
)
CSP_ENFORCE = os.getenv("REPGEN_CSP_ENFORCE", "").lower() in {"1", "true", "yes"}
SECURITY_HEADERS = {
    # Keep this conservative because the deployment may not own all subdomains.
    "Strict-Transport-Security": "max-age=31536000",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value

    csp_header = (
        "Content-Security-Policy" if CSP_ENFORCE else "Content-Security-Policy-Report-Only"
    )
    response.headers[csp_header] = CSP_POLICY
    return response

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for task status
# (In production, use Redis/db)
tasks: Dict[str, Dict[str, Any]] = {}


class ReproductionRequest(BaseModel):
    bug_report: str
    repo_url: Optional[str] = None
    backend: Literal["openai", "gemini", "claude"]
    model: str
    commit: Optional[str] = None
    api_key: Optional[str] = None


def _extract_json_payload(text: str) -> Dict[str, Any]:
    if not text:
        raise ValueError("Empty LLM response")
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except Exception:
        pass

    m = re.search(r"```json\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return json.loads(m.group(1))

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return json.loads(stripped[start : end + 1])

    raise ValueError("No JSON object found in LLM response")


def _numbered_code(code: str) -> str:
    return "\n".join([f"{i+1:4d}: {line}" for i, line in enumerate((code or "").splitlines())])


def _missing_coverage_ranges(code: str, annotations: list[Dict[str, Any]]) -> list[str]:
    lines = (code or "").splitlines()
    if not lines:
        return []

    required = {i + 1 for i, line in enumerate(lines) if line.strip()}
    covered = set()
    for ann in annotations:
        s = int(ann.get("start_line", 0))
        e = int(ann.get("end_line", 0))
        if s <= 0 or e <= 0:
            continue
        if e < s:
            s, e = e, s
        for line_no in range(s, e + 1):
            if line_no in required:
                covered.add(line_no)

    missing = sorted(required - covered)
    if not missing:
        return []

    ranges = []
    start = prev = missing[0]
    for n in missing[1:]:
        if n == prev + 1:
            prev = n
            continue
        ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
        start = prev = n
    ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
    return ranges


def extract_repo_url_from_bug_report(bug_report_url: str) -> Optional[str]:
    # Expected: https://github.com/{owner}/{repo}/issues/{num}
    m = re.search(r"https?://github\.com/([^/]+)/([^/]+)/issues/\d+", bug_report_url.strip(), re.IGNORECASE)
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    return f"https://github.com/{owner}/{repo}.git"


def run_reproduction_task(task_id: str, req: ReproductionRequest):
    service = RepGenService(output_dir="./repgen_results")

    tasks[task_id]["status"] = "running"

    def progress_cb(stage, msg, data=None):
        tasks[task_id]["logs"].append(f"[{stage}] {msg}")
        tasks[task_id]["stage"] = stage
        if data:
            if "artifacts" not in tasks[task_id]:
                tasks[task_id]["artifacts"] = {}
            if data["type"] == "refined_report":
                tasks[task_id]["artifacts"]["refined_report"] = data["content"]
            elif data["type"] == "plan":
                tasks[task_id]["artifacts"]["plan"] = data["content"]
            elif data["type"] == "code":
                tasks[task_id]["artifacts"]["code"] = data["content"]
            elif data["type"] == "context":
                tasks[task_id]["artifacts"]["context"] = data[
                    "content"
                ]  # Maybe accumulate? For now, last one.

    try:
        repo_source = req.repo_url or extract_repo_url_from_bug_report(req.bug_report)
        if not repo_source:
            raise RuntimeError("Could not determine repository from bug report URL. Please provide a GitHub issue URL.")

        result = service.run_reproduction(
            bug_report_source=req.bug_report,
            repo_source=repo_source,
            backend=req.backend,
            model=req.model,
            commit=req.commit,
            api_key=req.api_key,
            progress_callback=progress_cb,
        )

        if result["success"]:
            tasks[task_id]["status"] = "completed"
            tasks[task_id]["result"] = result[
                "files"
            ]  # This will now be a list of dicts {path, content}
        else:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["error"] = result["error"]

    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)


@app.post("/api/reproduce")
async def start_reproduction(
    req: ReproductionRequest, background_tasks: BackgroundTasks
):
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "status": "pending",
        "stage": "init",
        "logs": [],
        "artifacts": {},
        "result": None,
        "error": None,
    }

    background_tasks.add_task(run_reproduction_task, task_id, req)
    return {"task_id": task_id}


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]

class ExplainContextRequest(BaseModel):
    bug_report: str
    refined_report: Optional[str] = None
    context: str
    api_key: Optional[str] = None

class ExplainCodeRequest(BaseModel):
    bug_report: str
    refined_report: Optional[str] = None
    plan: Optional[str] = None
    code: str
    api_key: Optional[str] = None

@app.post("/api/explain/context")
async def explain_context(req: ExplainContextRequest):
    if not req.context:
        raise HTTPException(status_code=400, detail="Context is required")

    explanation_model = "gpt-4o"
    try:
        feedback = ""
        for attempt in range(2):
            explain_prompt = f"""You are an expert software engineer helping developers understand bug reproduction artifacts.

Return ONLY valid JSON. No markdown, no code fences, no commentary outside the JSON.

Schema:
{{
  "reasoning": "Step-by-step logical analysis of the bug, the context, and how it relates.",
  "context_summary": ["short point", "..."]
}}

Rules:
- reasoning must show deep analysis and step-by-step thought to ensure zero hallucination and high accuracy. DO not skip this.
- context_summary must have 3-5 short points (max 24 words each), plain text only.
- Each point must explicitly connect why the retrieve context is relevant to the bug.
- Mention concrete evidence such as file/snippet/dependency alignment.
{feedback}

Bug report:
{req.refined_report or req.bug_report}

Retrieved context JSON:
{req.context}
"""
            raw = query_llm(
                explain_prompt,
                backend="openai",
                model=explanation_model,
                api_key=req.api_key,
            )
            payload = _extract_json_payload(raw)
            if not isinstance(payload, dict):
                raise RuntimeError("LLM explanation payload was not an object")

            context_summary = []
            context_summary_raw = payload.get("context_summary") or []
            if isinstance(context_summary_raw, list):
                context_summary = [str(x).strip() for x in context_summary_raw if str(x).strip()][:5]

            if not context_summary:
                raise RuntimeError("LLM returned empty context_summary")

            break
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate LLM explanation for context: {e}") from e

    return {
        "model": explanation_model,
        "context_reason": " ".join(context_summary),
        "context_summary": context_summary,
    }


@app.post("/api/explain/code")
async def explain_code(req: ExplainCodeRequest):
    if not req.code:
        raise HTTPException(status_code=400, detail="Code is required")

    explanation_model = "gpt-4o"
    try:
        feedback = ""
        for attempt in range(2):
            explain_prompt = f"""You are an expert software engineer helping developers understand bug reproduction artifacts.

Return ONLY valid JSON. No markdown, no code fences, no commentary outside the JSON.

Schema:
{{
  "reasoning": "Step-by-step logical analysis of the bug and how the generated code reproduces it.",
  "code_annotations": [
    {{
      "label": "<label> (e.g., import, data loading, model definition, training loop, evaluation, etc.)",
      "start_line": 1,
      "end_line": 5,
      "explanation": "Precise, accurate explanation of what this block does to trigger the bug, if it does not, just describe the block."
    }}
  ]
}}

Rules:
- reasoning must show deep analysis and step-by-step thought to ensure zero hallucination and high accuracy. DO not skip this.
- code_annotations must have 4-12 entries.
- start_line/end_line must refer to the numbered code below.
- Cover all non-empty code lines at least once across annotations.
- Keep ranges meaningful and mostly non-overlapping.
- Explanations must be highly accurate and state exactly how that segment contributes to triggering, surfacing, or validating the bug.
{feedback}

Bug report:
{req.refined_report or req.bug_report}

Plan:
{req.plan or "N/A"}

Generated code (line-numbered):
{_numbered_code(req.code)}
"""
            raw = query_llm(
                explain_prompt,
                backend="openai",
                model=explanation_model,
                api_key=req.api_key,
            )
            payload = _extract_json_payload(raw)
            if not isinstance(payload, dict):
                raise RuntimeError("LLM explanation payload was not an object")

            code_annotations = []
            code_annotations_raw = payload.get("code_annotations") or []
            if isinstance(code_annotations_raw, list):
                for item in code_annotations_raw[:12]:
                    if not isinstance(item, dict):
                        continue
                    try:
                        s = int(item.get("start_line", 0))
                        e = int(item.get("end_line", 0))
                    except Exception:
                        continue
                    label = str(item.get("label", "")).strip() or "Code segment"
                    explanation = str(item.get("explanation", "")).strip()
                    if s <= 0 or e <= 0 or not explanation:
                        continue
                    if e < s:
                        s, e = e, s
                    code_annotations.append(
                        {"label": label, "start_line": s, "end_line": e, "explanation": explanation}
                    )

            if not code_annotations:
                raise RuntimeError("LLM returned empty code_annotations")

            missing_ranges = _missing_coverage_ranges(req.code, code_annotations)
            if missing_ranges and attempt == 0:
                feedback = (
                    "IMPORTANT RETRY FEEDBACK:\n"
                    f"- Missed non-empty code line ranges: {', '.join(missing_ranges)}.\n"
                    "- Regenerate annotations to cover all non-empty lines.\n"
                )
                continue

            break
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate LLM explanation for code: {e}") from e

    return {
        "model": explanation_model,
        "code_explanation": " ".join([ann["explanation"] for ann in code_annotations[:3]]),
        "code_annotations": code_annotations,
    }


ui_dist_dir = Path(__file__).resolve().parent.parent / "ui" / "dist"

if ui_dist_dir.exists():
    # Serve static assets generated by `npm --prefix ui run build`
    app.mount(
        "/assets", StaticFiles(directory=str(ui_dist_dir / "assets")), name="assets"
    )

    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(str(ui_dist_dir / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # Keep API routes handled by FastAPI endpoints above
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        target = ui_dist_dir / full_path
        if target.exists() and target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(ui_dist_dir / "index.html"))
