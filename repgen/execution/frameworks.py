"""Target Python framework registry.

The generation workflow lets the user pick a target framework before code is
generated. Each :class:`Framework` describes:

- the base dependencies to seed ``requirements.txt`` with,
- how to run the resulting program (execution command template),
- a minimal project scaffold (files created for a *new* local project),
- a testing configuration hint, and
- a short prompt fragment injected into generation so the model produces code
  that fits the chosen framework's conventions.

Frameworks are registered in ``FRAMEWORKS`` and looked up by name, so adding a
new one is a single dict entry — matching the provider-agnostic, extensible
style used for backends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ScaffoldFile:
    """A single file written when scaffolding a new project."""

    path: str
    content: str


@dataclass
class Framework:
    """A target framework and how RepGen should treat it."""

    name: str
    display_name: str
    dependencies: List[str] = field(default_factory=list)
    # Execution command template; ``{entry}`` is replaced with the entry script,
    # ``{python}`` with the venv python, ``{module}`` with the entry module name.
    run_template: List[str] = field(default_factory=lambda: ["{python}", "{entry}"])
    entrypoint: str = "main.py"
    test_command: List[str] = field(
        default_factory=lambda: ["{python}", "-m", "pytest", "-q"]
    )
    prompt_hint: str = ""
    scaffold: List[ScaffoldFile] = field(default_factory=list)

    def run_command(
        self, python: str, entry: str, module: Optional[str] = None
    ) -> List[str]:
        """Materialize the execution command for a concrete script/venv."""
        mod = module or entry.rsplit("/", 1)[-1].removesuffix(".py")
        return [
            part.replace("{python}", python)
            .replace("{entry}", entry)
            .replace("{module}", mod)
            for part in self.run_template
        ]

    def test_argv(self, python: str) -> List[str]:
        return [part.replace("{python}", python) for part in self.test_command]


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

FRAMEWORKS: Dict[str, Framework] = {
    "plain": Framework(
        name="plain",
        display_name="Plain Python",
        dependencies=[],
        run_template=["{python}", "{entry}"],
        entrypoint="main.py",
        prompt_hint=(
            "Target: a plain standalone Python script. Use only the standard "
            "library plus any packages that appear in the provided context."
        ),
        scaffold=[
            ScaffoldFile(
                "main.py",
                'def main() -> None:\n    print("hello from RepGen")\n\n\n'
                'if __name__ == "__main__":\n    main()\n',
            ),
            ScaffoldFile("requirements.txt", "# Project dependencies\n"),
            ScaffoldFile(
                "tests/test_main.py",
                "from main import main\n\n\ndef test_main_runs():\n    main()\n",
            ),
        ],
    ),
    "fastapi": Framework(
        name="fastapi",
        display_name="FastAPI",
        dependencies=["fastapi", "uvicorn[standard]", "httpx"],
        run_template=["{python}", "-m", "uvicorn", "{module}:app", "--port", "8000"],
        entrypoint="app.py",
        prompt_hint=(
            "Target: a FastAPI application. Expose an `app = FastAPI()` instance "
            "and define routes with async handlers. For a bug reproduction, use "
            "fastapi.testclient.TestClient / httpx to drive the endpoint in-process."
        ),
        scaffold=[
            ScaffoldFile(
                "app.py",
                "from fastapi import FastAPI\n\napp = FastAPI()\n\n\n"
                '@app.get("/")\ndef read_root():\n    return {"status": "ok"}\n',
            ),
            ScaffoldFile(
                "requirements.txt",
                "fastapi\nuvicorn[standard]\nhttpx\n",
            ),
            ScaffoldFile(
                "tests/test_app.py",
                "from fastapi.testclient import TestClient\n\n"
                "from app import app\n\n"
                "client = TestClient(app)\n\n\n"
                "def test_root():\n"
                '    resp = client.get("/")\n'
                "    assert resp.status_code == 200\n",
            ),
        ],
    ),
    "flask": Framework(
        name="flask",
        display_name="Flask",
        dependencies=["flask"],
        run_template=["{python}", "-m", "flask", "--app", "{module}", "run"],
        entrypoint="app.py",
        prompt_hint=(
            "Target: a Flask application. Create `app = Flask(__name__)` and "
            "register routes. For a bug reproduction use `app.test_client()` to "
            "drive endpoints in-process."
        ),
        scaffold=[
            ScaffoldFile(
                "app.py",
                "from flask import Flask\n\napp = Flask(__name__)\n\n\n"
                '@app.route("/")\ndef index():\n    return {"status": "ok"}\n',
            ),
            ScaffoldFile("requirements.txt", "flask\n"),
            ScaffoldFile(
                "tests/test_app.py",
                "from app import app\n\n\n"
                "def test_index():\n"
                "    client = app.test_client()\n"
                '    resp = client.get("/")\n'
                "    assert resp.status_code == 200\n",
            ),
        ],
    ),
    "django": Framework(
        name="django",
        display_name="Django",
        dependencies=["django"],
        run_template=["{python}", "manage.py", "runserver"],
        entrypoint="manage.py",
        test_command=["{python}", "manage.py", "test"],
        prompt_hint=(
            "Target: a Django project. Assume a standard project layout with "
            "manage.py and settings. For a bug reproduction, prefer a management "
            "command or Django's test runner (django.test.TestCase) so the ORM "
            "and settings are configured."
        ),
        scaffold=[
            ScaffoldFile(
                "requirements.txt",
                "django\n",
            ),
            ScaffoldFile(
                "README.md",
                "# Django project\n\n"
                "Run `django-admin startproject <name> .` inside the venv to "
                "scaffold, then `python manage.py runserver`.\n",
            ),
        ],
    ),
    "streamlit": Framework(
        name="streamlit",
        display_name="Streamlit",
        dependencies=["streamlit"],
        run_template=[
            "{python}",
            "-m",
            "streamlit",
            "run",
            "{entry}",
            "--server.headless",
            "true",
        ],
        entrypoint="app.py",
        prompt_hint=(
            "Target: a Streamlit app (script that calls st.* to build the UI). "
            "Note that a bug reproduction that must run headless should guard UI "
            "calls or exercise the underlying functions directly."
        ),
        scaffold=[
            ScaffoldFile(
                "app.py",
                "import streamlit as st\n\n"
                'st.title("RepGen Streamlit app")\n'
                'st.write("hello")\n',
            ),
            ScaffoldFile("requirements.txt", "streamlit\n"),
        ],
    ),
}

FRAMEWORK_NAMES = list(FRAMEWORKS.keys())
DEFAULT_FRAMEWORK = "plain"


def get_framework(name: Optional[str]) -> Framework:
    """Look up a framework by name, defaulting to plain Python."""
    if not name:
        return FRAMEWORKS[DEFAULT_FRAMEWORK]
    key = name.lower().strip()
    if key not in FRAMEWORKS:
        raise ValueError(
            f"Unknown framework '{name}'. Choose from: {', '.join(FRAMEWORK_NAMES)}"
        )
    return FRAMEWORKS[key]


def list_frameworks() -> List[Framework]:
    return list(FRAMEWORKS.values())
