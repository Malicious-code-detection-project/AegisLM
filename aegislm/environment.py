"""Load repository-local environment variables before external SDK imports."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_project_env(repo_root: Path | None = None) -> bool:
    """Load ``.env`` without replacing shell or CI-provided values."""
    root = repo_root or Path(__file__).resolve().parents[1]
    loaded = load_dotenv(root / ".env", override=False)
    # Require explicit HF_TOKEN use rather than silently borrowing a cached login.
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    return loaded
