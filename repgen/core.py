
import logging
import json
import os
import shutil
import subprocess
import time
import requests
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

from .retrieval.pipeline import RetrievalPipeline
from .utils import fetch_content, prepare_repository, checkout_commit, query_llm, create_prompt_refinement, create_prompt_plan, _build_prompt, check_structural_correctness, extract_json_content, check_relevance, clean_context

logger = logging.getLogger("repgen.core")

class RepGenService:
    def __init__(self, output_dir: str = "./repgen_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run_reproduction(self, 
                         bug_report_source: str, 
                         repo_source: str, 
                         backend: str, 
                         model: str, 
                         commit: Optional[str] = None,
                         max_attempts: int = 3,
                         api_key: Optional[str] = None,
                         progress_callback=None) -> Dict[str, Any]:
        """
        Executes the full reproduction pipeline.
        
        Args:
            bug_report_source: URL or path to bug report
            repo_source: URL or path to repository
            backend: LLM backend (ollama, openai, etc)
            model: Model name
            commit: Optional commit hash
            max_attempts: Max retry attempts per context
            api_key: Optional API key for backend
            progress_callback: Optional function(stage, message)
        
        Returns:
            Dict containing results and paths
        """
        result = {
            "success": False,
            "project_id": "",
            "files": [],
            "error": None
        }

        def notify(stage, msg, data=None):
            if progress_callback:
                progress_callback(stage, msg, data)
            logger.info(f"[{stage}] {msg}")

        try:
            # 1. Prepare Inputs
            notify("setup", "Fetching inputs...")
            bug_report_content = fetch_content(bug_report_source)
            local_repo_path = prepare_repository(repo_source)
            
            if commit:
                notify("setup", f"Checking out commit {commit}...")
                if not checkout_commit(local_repo_path, commit):
                    raise RuntimeError("Failed to checkout commit")

            # 2. Initialize Pipeline
            # Create a unique project ID/folder
            import time
            project_id = f"RepGen_Run_{int(time.time())}"
            run_dir = self.output_dir / project_id
            run_dir.mkdir(parents=True, exist_ok=True)
            
            local_bug_report_path = run_dir / "input_bug_report.txt"
            local_bug_report_path.write_text(bug_report_content)
            
            notify("retrieval", "Initializing Retrieval Pipeline...")
            pipeline = RetrievalPipeline(
                repo_path=local_repo_path,
                bug_report_path=str(local_bug_report_path),
                output_dir=str(self.output_dir) 
            )
            
            # 3. Retrieval
            notify("retrieval", "Running Code Retrieval...")
            ret_result = pipeline.run_pipeline()
            if not ret_result:
                raise RuntimeError("Retrieval failed to find relevant code")

            # 4. Refinement
            notify("refinement", "Refining Bug Report...")
            refined_report = query_llm(create_prompt_refinement(bug_report_content), backend, model, api_key=api_key)
            if not refined_report:
                refined_report = bug_report_content
            
            refined_path = pipeline.config.REFINED_BUG_REPORT_DIR_OUT / "refined_report.txt"
            refined_path.write_text(refined_report)
            notify("refinement", "Bug Report Refined", data={"type": "refined_report", "content": refined_report})

            # 5. Generation
            context_files = sorted(list(pipeline.config.CONTEXT_DIR_OUT.glob("*.json")))
            if not context_files:
                raise RuntimeError("No context files generated")

            notify("generation", f"Starting generation for {len(context_files)} contexts...")
            
            successful_gen = False
            generated_script_path = None
            
            for idx, ctx_file in enumerate(context_files, 1):
                ctx_num = ctx_file.stem.split('_')[-1]
                notify("generation", f"Processing Context {idx}/{len(context_files)}")
                
                with open(ctx_file, 'r') as f:
                    ctx_content = f.read()
                
                notify("generation", f"Context {ctx_num} Loaded", data={"type": "context", "content": clean_context(ctx_content), "index": idx})
                
                # Plan
                plan_raw = query_llm(create_prompt_plan(refined_report, json.loads(ctx_content)), backend, model, api_key=api_key)
                plan = extract_json_content(plan_raw) or "[]"
                notify("generation", f"Plan Generated for Context {ctx_num}", data={"type": "plan", "content": plan, "index": idx})
                
                prompt_code = _build_prompt(refined_report, ctx_content, plan)
                
                # Attempts
                for attempt in range(1, max_attempts + 1):
                    notify("generation", f"Context {ctx_num} - Attempt {attempt}")
                    
                    raw_code = query_llm(prompt_code, backend, model, api_key=api_key)
                    code = extract_json_content(raw_code) or raw_code
                    
                    is_valid, err = check_structural_correctness(code)
                    if err:
                        notify("generation", f"Context {ctx_num} - Attempt {attempt} - Syntax Error", data={"type": "feedback", "content": err, "code": code})
                        prompt_code = _build_prompt(refined_report, ctx_content, plan, feedback=f"Syntax Error: {err}")
                        continue
                        
                    if not check_relevance(refined_report, code, backend, model, api_key=api_key):
                        notify("generation", f"Context {ctx_num} - Attempt {attempt} - Irrelevant", data={"type": "feedback", "content": "Code deemed irrelevant", "code": code})
                        continue
                        
                    # Success
                    generated_script_path = pipeline.config.REPRODUCTION_DIR_OUT / f"reproduce_{ctx_num}.py"
                    generated_script_path.write_text(code)
                    
                    successful_gen = True
                    result["success"] = True
                    
                    result["files"].append({
                        "path": str(generated_script_path),
                        "content": code
                    })
                    notify("generation", "Reproduction Successful", data={"type": "code", "content": code, "path": str(generated_script_path)})
                    break
                
                if successful_gen:
                    break
            
            if not successful_gen:
                result["error"] = "Failed to generate valid script after all attempts"
                
            result["project_id"] = pipeline.config.PROJECT_ID
            return result

        except Exception as e:
            logger.exception("Reproduction failed")
            result["error"] = str(e)
            return result
