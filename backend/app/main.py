import os
import sys
from pathlib import Path

# Make the repository root importable when this module is executed from the backend folder.
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
for candidate in (str(REPO_ROOT), str(BACKEND_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from backend.main import app  # noqa: E402
