"""Input handling: fetching bug reports and preparing repositories."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import requests

from .console import console

logger = logging.getLogger("repgen.inputs")

GITHUB_ISSUE_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)")


def is_remote(source: str) -> bool:
    return source.startswith(("http://", "https://", "git@"))


def fetch_content(source: str) -> Tuple[str, Optional[str]]:
    """Fetch a bug report from a local file or URL.

    Returns ``(content, created_at)`` where ``created_at`` is the GitHub issue
    creation timestamp when available (used to time-travel the repo checkout).
    """
    if source.startswith(("http://", "https://")):
        match = GITHUB_ISSUE_RE.search(source)
        if match:
            owner, repo, issue_num = match.groups()
            api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_num}"
            console.log(f"[info]Fetching GitHub issue: {api_url}[/info]")
            headers = {}
            token = os.getenv("GITHUB_TOKEN")
            if token:
                headers["Authorization"] = f"Bearer {token}"
            response = requests.get(api_url, headers=headers, timeout=60)
            if response.status_code in (403, 404):
                console.log(
                    f"[warning]GitHub API returned {response.status_code}. "
                    "Set GITHUB_TOKEN for private/rate-limited access.[/warning]"
                )
            response.raise_for_status()
            data = response.json()
            title = data.get("title", "")
            body = data.get("body", "") or ""
            return f"Title: {title}\n\nBody:\n{body}", data.get("created_at")

        console.log(f"[info]Fetching URL: {source}[/info]")
        response = requests.get(source, timeout=60)
        response.raise_for_status()
        return response.text, None

    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"Local bug report not found: {path}")
    return path.read_text(encoding="utf-8"), None


def prepare_repository(source: str, temp_dir: Optional[str] = None) -> str:
    """Return an absolute local path to the repository.

    Remote URLs are cloned via a cached mirror (fast, offline-friendly). Local
    paths are validated and returned as-is.
    """
    if not is_remote(source):
        path = Path(source).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Repository path not found: {path}")
        return str(path)

    temp_dir = temp_dir or tempfile.mkdtemp(prefix="repgen_")
    repo_name = source.rstrip("/").split("/")[-1].replace(".git", "")
    local_path = Path(temp_dir) / repo_name
    if local_path.exists():
        console.log(f"[warning]{local_path} exists; reusing it.[/warning]")
        return str(local_path.resolve())

    cache_root = Path(
        os.getenv("REPGEN_REPO_CACHE_DIR", "~/.cache/repgen/repos")
    ).expanduser()
    cache_root.mkdir(parents=True, exist_ok=True)
    source_key = hashlib.sha1(source.strip().encode("utf-8")).hexdigest()[:12]
    mirror_path = cache_root / f"{repo_name}-{source_key}.git"

    try:
        if mirror_path.exists():
            console.log(f"[info]Updating cached mirror at {mirror_path}...[/info]")
            subprocess.run(
                ["git", "remote", "update", "--prune"],
                cwd=mirror_path,
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            console.log(f"[info]Cloning mirror for {source}...[/info]")
            subprocess.run(
                ["git", "clone", "--mirror", source, str(mirror_path)],
                check=True,
                capture_output=True,
                text=True,
            )
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or "").strip() or str(e)
        console.log(f"[warning]Mirror update failed: {detail}[/warning]")
        if not mirror_path.exists():
            raise RuntimeError(f"Failed to build repository cache: {detail}") from e

    try:
        subprocess.run(
            ["git", "clone", str(mirror_path), str(local_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        console.log("[success]Repository prepared.[/success]")
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or "").strip() or str(e)
        raise RuntimeError(f"Failed to clone from cache: {detail}") from e

    return str(local_path.resolve())


def checkout_commit(repo_path: str, commit: str) -> bool:
    """Checkout a specific commit. Returns ``True`` on success."""
    if not (Path(repo_path) / ".git").exists():
        logger.error("Not a git repository: %s", repo_path)
        return False
    try:
        subprocess.run(
            ["git", "checkout", commit],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        console.log(f"[success]Checked out {commit}[/success]")
        return True
    except subprocess.CalledProcessError as e:
        logger.error("git checkout failed: %s", (e.stderr or "").strip())
        return False


def checkout_to_date(repo_path: str, date_str: str) -> bool:
    """Checkout the latest commit before ``date_str`` (ISO timestamp)."""
    if not (Path(repo_path) / ".git").exists():
        logger.error("Not a git repository: %s", repo_path)
        return False
    try:
        result = subprocess.run(
            ["git", "rev-list", "-n", "1", f"--before={date_str}", "--all"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        commit_hash = result.stdout.strip()
        if not commit_hash:
            logger.warning("No commit found before %s", date_str)
            return False
        return checkout_commit(repo_path, commit_hash)
    except subprocess.CalledProcessError as e:
        logger.error("git rev-list failed: %s", (e.stderr or "").strip())
        return False
