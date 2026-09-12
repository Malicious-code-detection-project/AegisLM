"""Safe local artifact path validation and non-clobbering writers."""

from __future__ import annotations

from collections.abc import Iterable
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from aegislm.paths import is_git_safe_path


DEFAULT_JSON_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_JSONL_MAX_BYTES = 128 * 1024 * 1024
DEFAULT_JSONL_MAX_LINE_BYTES = 2 * 1024 * 1024
DEFAULT_JSONL_MAX_RECORDS = 100_000
DEFAULT_JSON_MAX_NESTING = 128


def validate_artifact_path_plan(
    *,
    inputs: Iterable[Path],
    outputs: Iterable[Path],
    protected_roots: Iterable[Path] = (),
    require_new: bool,
) -> None:
    """Reject unsafe, aliased, symlinked, or clobbering artifact paths."""
    input_paths = tuple(path.resolve(strict=False) for path in inputs)
    output_items = tuple(outputs)
    output_paths = tuple(path.resolve(strict=False) for path in output_items)
    roots = tuple(path.resolve(strict=False) for path in protected_roots)
    if len(set(output_paths)) != len(output_paths):
        raise ValueError("artifact output paths must be distinct")
    for path, resolved in zip(output_items, output_paths, strict=True):
        _validate_artifact_output_path(path)
        if require_new and path.exists():
            raise FileExistsError(f"artifact output already exists: {path}")
        if path.exists() and not path.is_file():
            raise ValueError("artifact file output must be a regular file")
        if resolved in input_paths:
            raise ValueError("artifact output must not alias an input")
        if any(resolved == root or resolved.is_relative_to(root) for root in roots):
            raise ValueError(
                "artifact output must be outside protected input directories"
            )


def write_text_artifact(path: Path, text: str, *, idempotent: bool = False) -> None:
    """Create an artifact without overwriting; optionally accept identical bytes."""
    encoded = text.encode("utf-8")
    # This validation intentionally happens before the idempotent early return:
    # an existing tracked file must never become an accepted artifact merely
    # because its bytes happen to match a requested report.
    _validate_artifact_output_path(path)
    if path.exists():
        if idempotent and path.is_file() and path.read_bytes() == encoded:
            return
        raise FileExistsError(f"artifact output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)


def validate_artifact_output_location(path: Path) -> None:
    """Validate one Git-safe, symlink-free artifact output location."""
    _validate_artifact_output_path(path)


def validate_no_symlink_components(path: Path, *, description: str = "path") -> None:
    """Reject a path when any existing component is a symbolic link."""
    if _has_symlink_component(path):
        raise ValueError(f"{description} must not traverse a symlink")


def load_bounded_json_object(
    path: Path,
    *,
    description: str,
    max_bytes: int = DEFAULT_JSON_MAX_BYTES,
) -> tuple[dict[str, Any], str]:
    """Load one regular UTF-8 JSON object with an exact-byte digest."""
    if max_bytes <= 0:
        raise ValueError("JSON byte limit must be positive")
    validate_no_symlink_components(path, description=description)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{description} must be a regular non-symlink file")
    with path.open("rb") as stream:
        payload = stream.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError(f"{description} exceeds the byte limit")
    try:
        value = strict_json_loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid {description} JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{description} must be a JSON object")
    return value, _sha256_bytes(payload)


def load_bounded_jsonl_objects(
    path: Path,
    *,
    description: str,
    max_bytes: int = DEFAULT_JSONL_MAX_BYTES,
    max_line_bytes: int = DEFAULT_JSONL_MAX_LINE_BYTES,
    max_records: int = DEFAULT_JSONL_MAX_RECORDS,
) -> tuple[list[dict[str, Any]], str]:
    """Strictly stream JSONL objects and return their exact-byte digest."""
    if min(max_bytes, max_line_bytes, max_records) <= 0:
        raise ValueError("JSONL limits must be positive")
    validate_no_symlink_components(path, description=description)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{description} must be a regular non-symlink file")
    rows: list[dict[str, Any]] = []
    total_bytes = 0
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            raw_line = stream.readline(max_line_bytes + 1)
            if not raw_line:
                break
            total_bytes += len(raw_line)
            if total_bytes > max_bytes:
                raise ValueError(f"{description} exceeds the total byte limit")
            if len(raw_line) > max_line_bytes:
                raise ValueError(f"{description} line exceeds the byte limit")
            digest.update(raw_line)
            if not raw_line.strip():
                continue
            if len(rows) >= max_records:
                raise ValueError(f"{description} exceeds the record limit")
            try:
                value = strict_json_loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                raise ValueError(
                    f"invalid {description} JSON at line {len(rows) + 1}"
                ) from exc
            if not isinstance(value, dict):
                raise ValueError(
                    f"{description} line {len(rows) + 1} must be a JSON object"
                )
            rows.append(value)
    return rows, digest.hexdigest()


def strict_json_loads(text: str | bytes | bytearray) -> Any:
    """Parse standards-compliant JSON and reject non-finite numbers recursively."""
    try:
        value = json.loads(text, parse_constant=_reject_json_constant)
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds the supported limit") from exc
    _validate_json_tree(value)
    return value


def json_dumps_artifact(value: Any, **kwargs: Any) -> str:
    """Serialize artifact data while rejecting NaN and Infinity."""
    return json.dumps(value, allow_nan=False, **kwargs)


def _validate_artifact_output_path(path: Path) -> None:
    resolved = path.resolve(strict=False)
    if not is_git_safe_path(str(resolved)):
        raise ValueError(
            "artifact output must be Git-ignored or outside the repository"
        )
    validate_no_symlink_components(path, description="artifact output")


def _has_symlink_component(path: Path) -> bool:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-standard JSON constants are not allowed")


def _validate_json_tree(value: Any) -> None:
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("JSON contains a non-finite number")
        if isinstance(item, dict):
            if depth >= DEFAULT_JSON_MAX_NESTING:
                raise ValueError("JSON nesting exceeds the supported limit")
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            if depth >= DEFAULT_JSON_MAX_NESTING:
                raise ValueError("JSON nesting exceeds the supported limit")
            pending.extend((child, depth + 1) for child in item)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
