import os
from pathlib import Path
from repgen.utils import prepare_repository

# Use the current repository path as a local repo
repo_path = str(Path(__file__).parent)
result = prepare_repository(repo_path)
print('Result path:', result)
print('Exists:', os.path.isdir(result))
