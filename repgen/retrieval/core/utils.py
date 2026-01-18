import ast
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import sys

def extract_module_path(file_path: str, dataset_root: str = "dataset/") -> str:
    """Extract full module path relative to dataset root."""
    try:
        file_path = os.path.normpath(file_path)
        dataset_root = os.path.normpath(dataset_root)
        parts = file_path.split(os.sep)
        
        try:
            root_idx = parts.index(dataset_root)
        except ValueError:
            return os.path.dirname(file_path)
            
        module_parts = parts[root_idx+1:-1]  # Exclude filename
        return os.path.join(*module_parts) if module_parts else "root"
    except Exception as e:
        logging.warning(f"Path parsing error {file_path}: {e}")
        return "unknown"

def load_bug_report(bug_report_path: Path) -> str:
    """Load bug report content."""
    try:
        with open(bug_report_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        raise ValueError(f"Error loading bug report: {str(e)}")

def save_json(data: Any, file_path: Path) -> None:
    """Save data to JSON file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def load_json(file_path: Path) -> Any:
    """Load data from JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def tokenize(text: str) -> List[str]:
    """Basic tokenizer for code search."""
    return re.findall(r'\b\w+[\w\d_]*\b', text.lower())
