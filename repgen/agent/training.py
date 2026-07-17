"""AST heuristic for detecting ML training loops.

Only the pure-AST :class:`TrainingLoopVisitor` remains; it powers the
``find_training_loops`` exploration tool and pulls in no heavy dependencies.
"""

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
        self.loop_depth = 0  # Track nested loops
        self.gradient_tape_depth = 0  # Track GradientTape contexts
        self.current_class = None  # Track class context

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
            if node.func.attr in {"item", "backward"} and self._is_loss_node(
                node.func.value
            ):
                self.found_training = True

            # DataLoader patterns
            if node.func.attr in {"to", "cuda"} and self._is_dataloader_node(
                node.func.value
            ):
                self.found_training = True

    # Helper methods -----------------------------------------------------------
    def _is_gradient_tape(self, node):
        """Identify GradientTape usage (direct or via tf.GradientTape)"""
        if isinstance(node, ast.Call):
            func = node.func
            return (
                isinstance(func, ast.Attribute) and func.attr == "GradientTape"
            ) or (isinstance(func, ast.Name) and func.id == "GradientTape")
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
