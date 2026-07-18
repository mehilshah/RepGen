"""Local project support for RepGen.

Extends the GitHub-centric workflow (``repgen.inputs.prepare_repository``) to
first-class *local* Python projects: opening an existing directory or creating a
new one scaffolded for a chosen framework. Both paths yield a
:class:`LocalProject` that the rest of the pipeline treats exactly like a
prepared repository, so the AI-assisted generation/execution experience is
identical whether the source is a cloned repo or a folder on disk.
"""

from __future__ import annotations

from .local import LocalProject, create_project, open_project

__all__ = ["LocalProject", "create_project", "open_project"]
