import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .core import RepGenService

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Preloading models...")
    from .retrieval.config import Config
    from .retrieval.models.hybrid_search import HybridSearchIndex
    
    config = Config(repo_path=".", bug_report_path="requirements.txt", output_dir="./repgen_results")
    _ = HybridSearchIndex(
        embedding_model=config.EMBEDDING_MODEL,
        reranker_model=config.RERANKER_MODEL,
        config=None,
    )
    print("Models preloaded successfully.")
    yield

app = FastAPI(title="RepGen API", lifespan=lifespan)

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
    repo_url: str
    backend: str = "openai"  # Default
    model: str = "gpt-4o"
    backend: str = "openai"  # Default
    model: str = "gpt-4o"
    commit: Optional[str] = None
    api_key: Optional[str] = None


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
                tasks[task_id]["artifacts"]["code_path"] = data["path"]
            elif data["type"] == "context":
                tasks[task_id]["artifacts"]["context"] = data[
                    "content"
                ]  # Maybe accumulate? For now, last one.

    try:
        result = service.run_reproduction(
            bug_report_source=req.bug_report,
            repo_source=req.repo_url,
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


# Serve UI (We will build this next)
# app.mount("/", StaticFiles(directory="ui/dist", html=True), name="ui")
