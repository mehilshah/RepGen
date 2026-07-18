"""RepGenService: orchestrates the exploration-based reproduction pipeline."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .agent.explorer import ExplorationAgent
from .agent.generator import ReproductionGenerator
from .agent.tools import RepoToolbox
from .backends import get_backend
from .inputs import (
    checkout_commit,
    checkout_to_date,
    fetch_content,
    prepare_repository,
)
from .prompts import refinement_prompt
from .reporting import write_run_report

logger = logging.getLogger("repgen.core")

ProgressCb = Optional[Callable[[str, Dict[str, Any]], None]]


class RepGenService:
    def __init__(self, output_dir: str = "./repgen_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run_reproduction(
        self,
        bug_report_source: str,
        repo_source: str,
        backend: str,
        model: Optional[str] = None,
        commit: Optional[str] = None,
        max_attempts: int = 3,
        max_explore_steps: int = 12,
        api_key: Optional[str] = None,
        progress_callback: ProgressCb = None,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "success": False,
            "project_id": "",
            "files": [],
            "error": None,
            "run_dir": None,
        }
        timings: Dict[str, float] = {}

        def notify(event: str, **data: Any) -> None:
            if progress_callback:
                progress_callback(event, data)

        try:
            client = get_backend(backend, model, api_key)

            # 1. Inputs
            notify("setup", message="Fetching bug report and repository...")
            t0 = time.time()
            bug_report_content, created_at = fetch_content(bug_report_source)
            local_repo_path = prepare_repository(repo_source)

            if commit:
                notify("setup", message=f"Checking out commit {commit}...")
                if not checkout_commit(local_repo_path, commit):
                    raise RuntimeError(f"Failed to checkout commit {commit}")
            elif created_at:
                notify("setup", message=f"Time-traveling repo to {created_at}...")
                checkout_to_date(local_repo_path, created_at)
            timings["setup"] = time.time() - t0

            project_id = f"RepGen_Run_{int(time.time())}"
            run_dir = self.output_dir / project_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "input_bug_report.txt").write_text(bug_report_content)
            result["project_id"] = project_id
            result["run_dir"] = str(run_dir)

            # 2. Refine bug report
            notify("refine", message="Refining bug report...")
            t0 = time.time()
            refined = client.generate(
                refinement_prompt(bug_report_content), max_tokens=1500
            ).text
            refined = refined or bug_report_content
            (run_dir / "refined_report.txt").write_text(refined)
            timings["refine"] = time.time() - t0
            notify("refine_done", refined=refined)

            # 3. Exploration
            notify("explore", message="Exploring repository...")
            t0 = time.time()
            toolbox = RepoToolbox(local_repo_path)
            explorer = ExplorationAgent(
                client,
                toolbox,
                max_steps=max_explore_steps,
                progress_cb=lambda ev, d: notify(f"explore.{ev}", **d),
            )
            context = explorer.explore(refined)
            timings["explore"] = time.time() - t0
            notify(
                "explore_done",
                files=context.key_files,
                symbols=list(context.symbol_index.all_symbols().keys()),
            )

            # 4. Generation + feedback loop
            notify("generate", message="Generating reproduction script...")
            t0 = time.time()
            generator = ReproductionGenerator(
                client, progress_cb=lambda ev, d: notify(f"generate.{ev}", **d)
            )
            gen = generator.generate(
                refined,
                context,
                max_attempts=max_attempts,
                explorer=explorer,
            )
            timings["generate"] = time.time() - t0

            # 5. Persist artifacts
            if gen.code:
                script_path = run_dir / "reproduce.py"
                script_path.write_text(gen.code)
                result["files"].append({"path": str(script_path), "content": gen.code})

            result["success"] = gen.success
            if not gen.success:
                result["error"] = (
                    "No attempt passed static verification; wrote best-effort script."
                    if gen.code
                    else "Failed to generate a reproduction script."
                )

            report_path = write_run_report(
                run_dir,
                backend=backend,
                model=client.model,
                refined_report=refined,
                context=context,
                generation=gen,
                timings=timings,
            )
            result["report"] = str(report_path)
            notify("done", success=gen.success, run_dir=str(run_dir))
            return result

        except Exception as e:  # noqa: BLE001 - surface a clean error to the CLI
            logger.exception("Reproduction failed")
            result["error"] = str(e)
            notify("error", message=str(e))
            return result
