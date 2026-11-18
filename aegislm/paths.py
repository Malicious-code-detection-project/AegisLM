"""Repository-aware path policy helpers without package-level dependencies."""

from __future__ import annotations

from pathlib import Path


def is_git_safe_path(path: str) -> bool:
    """Return whether a path resolves outside Git or under an ignored root."""
    candidate = Path(path).expanduser().resolve(strict=False)
    workspace_root = Path(__file__).resolve().parents[1]
    if not candidate.is_relative_to(workspace_root):
        return True
    rel_path = candidate.relative_to(workspace_root)
    top_dir = rel_path.parts[0] if rel_path.parts else ""
    return top_dir in {
        "data",
        "raw_datasets",
        "artifacts",
        "checkpoints",
        "adapters",
        "models",
        "outputs",
        "runs",
        "experiments",
    }
