import os
from pathlib import Path


class Config:
    def __init__(self, repo_path: str, bug_report_path: str, output_dir: str):

        self.BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent

        self.CODE_DIR = Path(repo_path).resolve()
        self.BUG_REPORT_FILE = Path(bug_report_path).resolve()
        self.OUTPUT_DIR = Path(output_dir).resolve()

        # Unique project identifier based on repo name and bug report name
        self.PROJECT_ID = f"{self.CODE_DIR.name}_{self.BUG_REPORT_FILE.stem}"
        self.PROJECT_DIR = self.OUTPUT_DIR / self.PROJECT_ID

        # --- Base paths for outputs ---
        self.REFINED_BUG_REPORT_DIR = self.PROJECT_DIR / "refined_bug_report"
        self.CONTEXT_DIR = self.PROJECT_DIR / "context"
        self.PLANS_DIR = self.PROJECT_DIR / "plan"
        self.REPRODUCTION_DIR = self.PROJECT_DIR / "reproduction_code"

        # Set IN/OUT paths to the same consolidated directories
        self.REFINED_BUG_REPORT_DIR_IN = self.REFINED_BUG_REPORT_DIR
        self.REFINED_BUG_REPORT_DIR_OUT = self.REFINED_BUG_REPORT_DIR
        self.CONTEXT_DIR_IN = self.CONTEXT_DIR
        self.CONTEXT_DIR_OUT = self.CONTEXT_DIR
        self.PLANS_DIR_IN = self.PLANS_DIR
        self.PLANS_DIR_OUT = self.PLANS_DIR
        self.REPRODUCTION_DIR_OUT = self.REPRODUCTION_DIR

        # Model configurations
        self.EMBEDDING_MODEL = (
            "flax-sentence-embeddings/st-codesearch-distilroberta-base"
        )
        self.RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

        # Search parameters
        self.SEARCH_TOP_K = 200
        self.RERANK_TOP_K = 20
        self.ALPHA = 0.55

        # Ensure directories exist
        self._setup_directories()

    def _setup_directories(self):
        # Ensure base directories exist
        self.PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        self.REFINED_BUG_REPORT_DIR.mkdir(parents=True, exist_ok=True)
        self.CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        self.PLANS_DIR.mkdir(parents=True, exist_ok=True)
        self.REPRODUCTION_DIR.mkdir(parents=True, exist_ok=True)
