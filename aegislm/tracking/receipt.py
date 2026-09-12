"""Atomic local receipts for retry-safe W&B linkage."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from contextlib import contextmanager
import fcntl
from pathlib import Path
from threading import Lock
from typing import Any, BinaryIO, Iterator
from urllib.parse import urlparse

from aegislm.artifacts import validate_artifact_path_plan

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY = re.compile(r"^[0-9a-f]{16}$")
MAX_RECEIPT_BYTES = 64 * 1024


class TrackingReceiptClaim:
    """Process-lifetime exclusive right to perform one receipt's remote work."""

    def __init__(
        self,
        *,
        path: Path,
        base: Mapping[str, Any],
        resume: str,
        status: str,
        tracking: Mapping[str, Any] | None,
        lock_stream: BinaryIO,
    ) -> None:
        self.path = path
        self.base = dict(base)
        self.resume = resume
        self.status = status
        self._needs_logging = status == "pending"
        self.tracking = dict(tracking) if tracking is not None else None
        self._lock_stream: BinaryIO | None = lock_stream
        with _ACTIVE_CLAIMS_LOCK:
            _ACTIVE_CLAIMS.add(self)

    @property
    def needs_logging(self) -> bool:
        """Whether the remote payload has not yet reached W&B."""
        return self._needs_logging

    def close(self) -> None:
        """Release the inter-process claim exactly once."""
        stream = self._lock_stream
        if stream is None:
            return
        self._lock_stream = None
        with _ACTIVE_CLAIMS_LOCK:
            _ACTIVE_CLAIMS.discard(self)
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()

    def __del__(self) -> None:
        self.close()


_ACTIVE_CLAIMS: set[TrackingReceiptClaim] = set()
_ACTIVE_CLAIMS_LOCK = Lock()


def build_tracking_receipt(kind: str, source_sha256: str) -> dict[str, Any]:
    """Build a deterministic, path-free receipt identity."""
    if kind not in {"evaluation", "comparison", "training", "gate"}:
        raise ValueError("unsupported W&B receipt kind")
    if _SHA256.fullmatch(source_sha256) is None:
        raise ValueError("W&B receipt source digest must be SHA-256")
    identity = hashlib.sha256(f"{kind}\0{source_sha256}".encode()).hexdigest()[:16]
    return {
        "kind": kind,
        "identity": identity,
        "source_sha256": source_sha256,
    }


def tracking_payload_sha256(value: Mapping[str, Any]) -> str:
    """Hash immutable, path-free run metadata into a receipt source identity."""
    encoded = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def prepare_tracking_receipt(
    path: Path,
    base: Mapping[str, Any],
    *,
    ambiguous_resolution: str | None = None,
) -> TrackingReceiptClaim | None:
    """Acquire exclusive remote-work ownership and prepare retry state."""
    _validate_receipt_base(base)
    pending = {**base, "status": "pending"}
    _validate_receipt_path(path)
    lock_stream = _acquire_receipt_claim_lock(path)
    try:
        if ambiguous_resolution is not None and not path.exists():
            raise ValueError(
                "W&B reconciliation requires an existing logging_ambiguous receipt"
            )
        if _create_pending_receipt_exclusive(path, pending):
            return TrackingReceiptClaim(
                path=path,
                base=base,
                resume="never",
                status="pending",
                tracking=None,
                lock_stream=lock_stream,
            )
        existing = _load_receipt(path)
        for key in ("kind", "identity", "source_sha256"):
            if existing.get(key) != base.get(key):
                raise ValueError("existing W&B receipt is for a different local result")
        status = existing.get("status")
        if status == "complete":
            if ambiguous_resolution is not None:
                raise ValueError(
                    "W&B reconciliation is valid only for logging_ambiguous receipts"
                )
            _release_lock_stream(lock_stream)
            return None
        if status == "logging_ambiguous":
            if ambiguous_resolution is None:
                raise RuntimeError(
                    "W&B logging outcome is ambiguous; explicitly choose "
                    "--wandb-reconcile retry-logging or finish-only"
                )
            if ambiguous_resolution == "retry-logging":
                _replace_receipt(path, pending)
                existing = pending
                status = "pending"
            elif ambiguous_resolution != "finish-only":
                raise ValueError("invalid W&B ambiguous-state resolution")
        elif ambiguous_resolution is not None:
            raise ValueError(
                "W&B reconciliation is valid only for logging_ambiguous receipts"
            )
        if status not in {"pending", "logging_ambiguous", "logged_pending_finish"}:
            raise ValueError("existing W&B receipt has an invalid status")
        return TrackingReceiptClaim(
            path=path,
            base=base,
            resume="allow",
            status=str(status),
            tracking=(
                existing.get("tracking")
                if isinstance(existing.get("tracking"), Mapping)
                else None
            ),
            lock_stream=lock_stream,
        )
    except BaseException:
        _release_lock_stream(lock_stream)
        raise


def finish_with_tracking_receipt(
    claim: TrackingReceiptClaim,
    reference: Mapping[str, Any],
    finish: Callable[[int], None],
) -> None:
    """Persist linkage before finish and completion only after finish succeeds."""
    if not isinstance(claim, TrackingReceiptClaim) or claim._lock_stream is None:
        raise ValueError("an active W&B receipt claim is required")
    path = claim.path
    base = claim.base
    try:
        if claim.status not in {"logging_ambiguous", "logged_pending_finish"}:
            raise ValueError(
                "W&B receipt must mark logging started before remote finish"
            )
        _validate_receipt_base(base)
        _validate_tracking_reference(reference, expected_run_id=_expected_run_id(base))
        if claim.tracking is not None and claim.tracking != dict(reference):
            raise ValueError("W&B recovery reference does not match the logged receipt")
        logged = {
            **base,
            "status": "logged_pending_finish",
            "tracking": dict(reference),
        }
        _write_claimed_tracking_receipt(path, logged)
        finish(0)
        _write_claimed_tracking_receipt(path, {**logged, "status": "complete"})
    finally:
        claim.close()


def mark_tracking_logging_started(claim: TrackingReceiptClaim) -> None:
    """Persist the uncertain remote-ack boundary before the first payload log."""
    if not isinstance(claim, TrackingReceiptClaim) or claim._lock_stream is None:
        raise ValueError("an active W&B receipt claim is required")
    if claim.status != "pending":
        raise ValueError("W&B logging can start only from pending state")
    ambiguous = {**claim.base, "status": "logging_ambiguous"}
    _write_claimed_tracking_receipt(claim.path, ambiguous)
    claim.status = "logging_ambiguous"


def write_tracking_receipt(path: Path, value: Mapping[str, Any]) -> None:
    """Atomically replace a receipt without exposing local artifact paths."""
    _validate_receipt(value)
    _validate_receipt_path(path)
    with _receipt_lock(path):
        if path.exists():
            existing = _load_receipt(path)
            for key in ("kind", "identity", "source_sha256"):
                if existing.get(key) != value.get(key):
                    raise ValueError("existing W&B receipt has a different identity")
            status_order = {
                "pending": 0,
                "logging_ambiguous": 1,
                "logged_pending_finish": 2,
                "complete": 3,
            }
            if (
                status_order[str(value["status"])]
                < status_order[str(existing["status"])]
            ):
                raise ValueError("W&B receipt status cannot move backwards")
        _replace_receipt(path, value)


def release_active_tracking_claims() -> None:
    """Release claims only after the caller finishes any active W&B run."""
    with _ACTIVE_CLAIMS_LOCK:
        claims = tuple(_ACTIVE_CLAIMS)
    for claim in claims:
        claim.close()


def _write_claimed_tracking_receipt(path: Path, value: Mapping[str, Any]) -> None:
    """Write while the caller retains the process-lifetime receipt claim."""
    _validate_receipt(value)
    _validate_receipt_path(path)
    if path.exists():
        existing = _load_receipt(path)
        for key in ("kind", "identity", "source_sha256"):
            if existing.get(key) != value.get(key):
                raise ValueError("existing W&B receipt has a different identity")
        status_order = {
            "pending": 0,
            "logging_ambiguous": 1,
            "logged_pending_finish": 2,
            "complete": 3,
        }
        if status_order[str(value["status"])] < status_order[str(existing["status"])]:
            raise ValueError("W&B receipt status cannot move backwards")
    _replace_receipt(path, value)


def _replace_receipt(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                dict(value), stream, indent=2, ensure_ascii=False, allow_nan=False
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_receipt(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("W&B receipt must be a regular non-symlink file")
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_RECEIPT_BYTES + 1)
        if len(payload) > MAX_RECEIPT_BYTES:
            raise ValueError("W&B receipt exceeds the byte limit")
        value = json.loads(payload, parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("invalid W&B receipt JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("W&B receipt must be a JSON object")
    _validate_receipt(value)
    return value


def _create_pending_receipt_exclusive(path: Path, value: Mapping[str, Any]) -> bool:
    """Atomically publish the first complete receipt without a write race."""
    _validate_receipt(value)
    _validate_receipt_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".pending.tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                dict(value), stream, indent=2, ensure_ascii=False, allow_nan=False
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # link(2) is an atomic create-if-absent operation. Unlike writing the
        # O_EXCL target directly, it never lets another caller read a partial
        # first receipt between creation and fsync.
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            return False
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _validate_receipt_base(base: Mapping[str, Any]) -> None:
    if not isinstance(base, Mapping):
        raise ValueError("W&B receipt base must be a mapping")
    if base.get("kind") not in {"evaluation", "comparison", "training", "gate"}:
        raise ValueError("W&B receipt has an invalid kind")
    if (
        not isinstance(base.get("identity"), str)
        or _IDENTITY.fullmatch(base["identity"]) is None
    ):
        raise ValueError("W&B receipt has an invalid identity")
    if (
        not isinstance(base.get("source_sha256"), str)
        or _SHA256.fullmatch(base["source_sha256"]) is None
    ):
        raise ValueError("W&B receipt has an invalid source digest")


def _validate_tracking_reference(
    reference: Mapping[str, Any], *, expected_run_id: str
) -> None:
    if not isinstance(reference, Mapping):
        raise ValueError("W&B receipt tracking reference must be a mapping")
    for key in ("run_id", "run_url"):
        if not isinstance(reference.get(key), str) or not reference[key]:
            raise ValueError(f"W&B receipt tracking reference requires {key}")
    if reference["run_id"] != expected_run_id:
        raise ValueError("W&B receipt tracking run ID does not match its identity")
    parsed = urlparse(reference["run_url"])
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or expected_run_id not in parsed.path.split("/")
    ):
        raise ValueError("W&B receipt tracking run URL does not match its identity")


def _validate_receipt(value: Mapping[str, Any]) -> None:
    _validate_receipt_base(value)
    status = value.get("status")
    if status not in {
        "pending",
        "logging_ambiguous",
        "logged_pending_finish",
        "complete",
    }:
        raise ValueError("W&B receipt has an invalid status")
    tracking = value.get("tracking")
    if status in {"pending", "logging_ambiguous"}:
        if tracking is not None:
            raise ValueError(
                "pre-log W&B receipt must not contain a tracking reference"
            )
        return
    if not isinstance(tracking, Mapping):
        raise ValueError("completed W&B receipt requires a tracking reference")
    _validate_tracking_reference(tracking, expected_run_id=_expected_run_id(value))


def _expected_run_id(value: Mapping[str, Any]) -> str:
    _validate_receipt_base(value)
    return f"source-v2-{value['kind']}-{value['identity']}"


def tracking_run_id(value: Mapping[str, Any]) -> str:
    """Return the deterministic W&B run ID bound to a validated receipt base."""
    return _expected_run_id(value)


def _validate_receipt_path(path: Path) -> None:
    validate_artifact_path_plan(inputs=(), outputs=(path,), require_new=False)


@contextmanager
def _receipt_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_name(f".{path.name}.lock")
    validate_artifact_path_plan(inputs=(), outputs=(lock_path,), require_new=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _acquire_receipt_claim_lock(path: Path) -> BinaryIO:
    lock_path = path.with_name(f".{path.name}.lock")
    validate_artifact_path_plan(inputs=(), outputs=(lock_path,), require_new=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = lock_path.open("a+b")
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        stream.close()
        raise RuntimeError("W&B receipt is already owned by another process") from exc
    return stream


def _release_lock_stream(stream: BinaryIO) -> None:
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        stream.close()


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-standard JSON constants are not allowed")
