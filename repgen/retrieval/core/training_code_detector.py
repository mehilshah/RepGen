import ast
from pathlib import Path
from typing import List, Dict, Tuple, Any
import numpy as np
from sentence_transformers import CrossEncoder
from transformers import AutoTokenizer
import torch
import os
import logging

logger = logging.getLogger(__name__)

import ast

class TrainingLoopVisitor(ast.NodeVisitor):
    """
    AST visitor to detect training loops in:
    - TensorFlow 1.x (Session.run in loops)
    - TensorFlow 2.x (Keras APIs, GradientTape, and optimizer methods)
    - PyTorch (optimizer steps in loops, DataLoader usage)
    - PyTorch Lightning (training_step method)
    """
    
    def __init__(self):
        # Framework flags
        self.found_training = False
        
        # Context tracking
        self.loop_depth = 0               # Track nested loops
        self.gradient_tape_depth = 0       # Track GradientTape contexts
        self.current_class = None          # Track class context

    # Context management ------------------------------------------------------
    def visit_ClassDef(self, node):
        """Track class context for LightningModule detection"""
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = None

    def visit_For(self, node):
        self.loop_depth += 1
        self.generic_visit(node)
        self.loop_depth -= 1

    def visit_While(self, node):
        self.loop_depth += 1
        self.generic_visit(node)
        self.loop_depth -= 1

    def visit_With(self, node):
        """Handle GradientTape and PyTorch profiler contexts"""
        # Check for GradientTape first
        if any(self._is_gradient_tape(item.context_expr) for item in node.items):
            self.gradient_tape_depth += 1
            self.generic_visit(node)
            self.gradient_tape_depth -= 1
        else:
            self.generic_visit(node)

    # Core detection logic -----------------------------------------------------
    def visit_Call(self, node):
        """Analyze method calls for framework patterns"""
        self._check_tf1_patterns(node)
        self._check_tf2_patterns(node)
        self._check_pytorch_patterns(node)
        self.generic_visit(node)

    def _check_tf1_patterns(self, node):
        """TensorFlow 1.x: Session.run in loops with training ops"""
        if self.loop_depth > 0:
            if isinstance(node.func, ast.Attribute) and node.func.attr == "run":
                # Basic check for Session-like objects
                if isinstance(node.func.value, (ast.Name, ast.Attribute)):
                    self.found_training = True

    def _check_tf2_patterns(self, node):
        """TensorFlow 2.x detection"""
        if isinstance(node.func, ast.Attribute):
            # High-level APIs
            if node.func.attr in {"fit", "fit_generator", "train_on_batch"}:
                self.found_training = True
            
            # Optimizer methods
            if node.func.attr in {"apply_gradients", "minimize"}:
                self.found_training = True
            
            # GradientTape context patterns
            if self.gradient_tape_depth > 0:
                if node.func.attr in {"gradient", "watch"}:
                    self.found_training = True

    def _check_pytorch_patterns(self, node):
        """PyTorch detection: Training steps in loops"""
        if self.loop_depth > 0 and isinstance(node.func, ast.Attribute):
            # Core training methods
            if node.func.attr in {"backward", "step", "zero_grad"}:
                self.found_training = True
                
            # Loss calculation patterns
            if node.func.attr in {"item", "backward"} and \
                self._is_loss_node(node.func.value):
                self.found_training = True

            # DataLoader patterns
            if node.func.attr in {"to", "cuda"} and \
                self._is_dataloader_node(node.func.value):
                self.found_training = True

    # Helper methods -----------------------------------------------------------
    def _is_gradient_tape(self, node):
        """Identify GradientTape usage (direct or via tf.GradientTape)"""
        if isinstance(node, ast.Call):
            func = node.func
            return (
                (isinstance(func, ast.Attribute) and func.attr == "GradientTape") or
                (isinstance(func, ast.Name) and func.id == "GradientTape")
            )
        return False

    def _is_loss_node(self, node):
        """Heuristic to identify loss nodes (e.g., 'loss' in names)"""
        if isinstance(node, ast.Name):
            return "loss" in node.id.lower()
        elif isinstance(node, ast.Attribute):
            return "loss" in node.attr.lower()
        return False

    def _is_dataloader_node(self, node):
        """Heuristic to identify DataLoader instances"""
        if isinstance(node, ast.Name):
            return "loader" in node.id.lower() or "dataloader" in node.id.lower()
        elif isinstance(node, ast.Attribute):
            return "loader" in node.attr.lower() or "dataloader" in node.attr.lower()
        return False

    # PyTorch Lightning support -----------------------------------------------
    def visit_FunctionDef(self, node):
        """Check for LightningModule training_step hooks"""
        if self.current_class and node.name == "training_step":
            self.found_training = True
        self.generic_visit(node)

class TrainingCodeDetector:
    def __init__(self, config):
        self.config = config
        self.reranker = CrossEncoder(config.RERANKER_MODEL)
        self.tokenizer = AutoTokenizer.from_pretrained(config.RERANKER_MODEL)
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.reranker.to(self.device)

    def contains_training(self, file_path: Path) -> bool:
        """Check if a file contains training-related code using AST analysis."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
            tree = ast.parse(code)
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {str(e)}")
            return False

        visitor = TrainingLoopVisitor()
        visitor.visit(tree)
        return visitor.found_training

    def _get_all_files(self, module_report: Dict[str, Any]) -> List[Path]:
        """Get all Python files from modules in the report."""
        # --- MODIFICATION: Ablation: No Module-Centric Partitioning ---
        files = set() # Use set to avoid duplicates

        files = set() # Use set to avoid duplicates

        # Original: Walk all files in the retrieved modules' directories
        for module in module_report['modules']:
            module_path = self.config.CODE_DIR / module['module']
            if not module_path.exists():
                continue
                
            for root, _, filenames in os.walk(module_path):
                for filename in filenames:
                    if filename.endswith('.py'):
                        files.add(Path(root) / filename)
        
        return list(files)

    def _rank_files(self, files: List[Path], bug_report: str) -> List[Tuple[Path, float]]:
        """Rank files by relevance to the bug report."""
        if not files:
            return []
            
        # Tokenize with proper truncation
        features = self.tokenizer(
            [bug_report[:100000]] * len(files),
            [file.read_text(encoding='utf-8')[:100000] for file in files],
            padding=True,
            truncation='longest_first',
            max_length=512,
            return_tensors="pt"
        ).to(self.device)
        
        # Run cross-encoder
        with torch.no_grad():
            scores = self.reranker(**features).logits.squeeze().cpu().numpy()
        
        # Normalize scores
        if len(scores) > 1:
            scores = (scores - scores.min()) / (scores.max() - scores.min() + 1e-8)
        
        return sorted(zip(files, scores), key=lambda x: x[1], reverse=True)

    def detect_training_code(self, module_report: Dict[str, Any], bug_report_path: Path) -> Dict[str, Any]:
        """Detect and rank training-related code."""
        bug_report = bug_report_path.read_text(encoding='utf-8')
        all_files = self._get_all_files(module_report)
        
        training_files = []
        training_files = []
        for file in all_files:
            if self.contains_training(file):
                training_files.append(file)
        
        # Original ranking logic
        ranked_files = self._rank_files(training_files, bug_report)
        # --- END MODIFICATION ---
        
        return {
            'bug_report': module_report['bug_report'],
            'training_files': [
                {
                    'file': str(file.relative_to(self.config.CODE_DIR)),
                    'score': float(score),
                    'contains_training': True
                }
                for file, score in ranked_files
            ]
        }