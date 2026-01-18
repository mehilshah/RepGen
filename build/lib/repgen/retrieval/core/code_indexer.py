import ast
import os
import time
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..models.hybrid_search import HybridSearchIndex
from .utils import tokenize, save_json, load_json
import logging

logger = logging.getLogger(__name__)

class CodeIndexer:
    def __init__(self, config):
        self.config = config

    def _load_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Load a single file and return as document."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return {
                    'page_content': f.read(),
                    'metadata': {
                        'source': str(file_path),
                        'type': 'file'
                    }
                }
        except Exception as e:
            logger.warning(f"Error loading {file_path}: {e}")
            return None

    def _semantic_chunking(self, doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Split code into semantic chunks (functions, classes)."""
        chunks = []
        file_path = doc['metadata']['source']
        code = doc['page_content']
        
        try:
            tree = ast.parse(code)
            current_chunk = []
            
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    start_lineno = node.lineno - 1
                    end_lineno = node.end_lineno if hasattr(node, 'end_lineno') else start_lineno + 1
                    chunk_code = "\n".join(code.splitlines()[start_lineno:end_lineno])
                    current_chunk.append(chunk_code)
                    
                    if len(current_chunk) >= 3:
                        chunk = {
                            'page_content': "\n\n".join(current_chunk),
                            'metadata': {
                                'source': file_path,
                                'type': 'semantic_chunk',
                                'start_line': start_lineno + 1,
                                'end_line': end_lineno
                            }
                        }
                        chunks.append(chunk)
                        current_chunk = []
            
            if current_chunk:
                chunk = {
                    'page_content': "\n\n".join(current_chunk),
                    'metadata': {
                        'source': file_path,
                        'type': 'semantic_chunk',
                        'start_line': start_lineno + 1,
                        'end_line': end_lineno
                    }
                }
                chunks.append(chunk)
                
        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
        
        return chunks

    def _process_codebase(self, code_dir: Path) -> tuple[List[Dict[str, Any]], List[List[str]]]:
        """Process all files in the code directory."""
        files = [f for f in code_dir.glob("**/*.py") 
                if "__pycache__" not in str(f) and not any(part.startswith('.') for part in f.parts)]
        
        with Pool(cpu_count()) as pool:
            docs = pool.map(self._load_file, files)
        
        valid_docs = [doc for doc in docs if doc is not None]
        chunks = []
        for doc in valid_docs:
            chunks.extend(self._semantic_chunking(doc))
        
        corpus = [tokenize(chunk['page_content']) for chunk in chunks]
        return chunks, corpus

    def index_codebase(self, code_dir: Path) -> HybridSearchIndex:
        """Index the codebase for hybrid search."""
        start_time = time.time()
        index_dir = self.config.PROJECT_DIR / "hybrid_index"
        
        hybrid_index = HybridSearchIndex(
            embedding_model=self.config.EMBEDDING_MODEL,
            reranker_model=self.config.RERANKER_MODEL,
            config = self.config
        )
        
        if (index_dir / "documents.json").exists():
            logger.info("Loading existing index")
            hybrid_index.load_index(index_dir)
            return hybrid_index
            
        logger.info("Building new index")
        chunks, corpus = self._process_codebase(code_dir)
        hybrid_index.build_index(chunks, corpus)
        hybrid_index.save_index(index_dir)
        
        logger.info(f"Indexing completed in {time.time()-start_time:.2f}s")
        return hybrid_index

    def find_relevant_code(self, bug_report: str, hybrid_index: HybridSearchIndex) -> List[dict]:
        """Find code relevant to the bug report."""
        return hybrid_index.search(
            bug_report,
            top_k=self.config.SEARCH_TOP_K,
            rerank_top_k=self.config.RERANK_TOP_K,
            alpha=self.config.ALPHA
        )