# Contributing to RepGen

Thank you for your interest in contributing!

## Code Quality

We use a set of tools to ensure high code quality:
- **Black**: For concise and consistent code formatting in Python.
- **Isort**: For sorting imports.
- **Flake8**: For linting.
- **Mypy**: For static type checking.

These checks are automatically run in our CI pipeline.

## Local Development

To run these checks locally, we recommend using `pre-commit`.

1. **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2. **Install git hooks**:
    ```bash
    pre-commit install
    ```

Now, every time you commit, `pre-commit` will automatically format your code and check for issues.

You can also run it manually at any time:
```bash
pre-commit run --all-files
```
