"""Import the historical source-v2 canary curve and aggregate gate to W&B."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
import fcntl
from pathlib import Path
from threading import Lock
from typing import Any, BinaryIO, Iterator
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aegislm.environment import load_project_env  # noqa: E402

load_project_env(REPO_ROOT)

EXPECTED_BASE_MODEL_ID = "openai/gpt-oss-20b"
EXPECTED_RUNTIME_MODEL_ID = "unsloth/gpt-oss-20b-unsloth-bnb-4bit"
EXPECTED_RUNTIME_REVISION = "093fba6992ef5a7152481afec0bdfca1ac486998"
EXPECTED_HISTORY_STEPS = 125
EXPECTED_TRAIN_RECORDS_SHA256 = (
    "e945b83777119d809dd2f9a7c6b638c0e1b2815af1fc1fd1ea8fb741550f155d"
)
EXPECTED_VALIDATION_RECORDS_SHA256 = (
    "45989ea9e3a81926f13cfe73a8088d44b8b7817fcb782fd61f3ffd6b3d1b40d0"
)
EXPECTED_GATE_CONFIG_SHA256 = (
    "987cc195a8750827ec86a6196d9184bc523ef690efb31796467ab70dc1c193a4"
)
EXPECTED_SOURCE_DIGESTS = {
    "trainer_state_sha256": (
        "d434757331a7a48fd98c8194a8107829cf7d3d7646b6bcb0f4a82e6b0e4b22f2"
    ),
    "manifest_sha256": (
        "3e0e8adf07cecd235b0377c5b8d08bb5bfb97ece45a98c8425553c83278642e4"
    ),
    "gate_report_sha256": (
        "2b730289b0f96fdac1d2896fac6a15f4428cabba3dfc993e69852a3a0d7b989c"
    ),
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class _HistoricalReceiptClaim:
    """Exclusive ownership of one historical-import remote side effect."""

    def __init__(
        self,
        path: Path,
        resume: str,
        status: str,
        tracking: dict[str, Any] | None,
        stream: BinaryIO,
    ) -> None:
        self.path = path
        self.resume = resume
        self.status = status
        self._needs_logging = status == "pending"
        self.tracking = dict(tracking) if tracking is not None else None
        self._stream: BinaryIO | None = stream
        with _ACTIVE_HISTORICAL_CLAIMS_LOCK:
            _ACTIVE_HISTORICAL_CLAIMS.add(self)

    @property
    def needs_logging(self) -> bool:
        return self._needs_logging

    def close(self) -> None:
        stream = self._stream
        if stream is None:
            return
        self._stream = None
        with _ACTIVE_HISTORICAL_CLAIMS_LOCK:
            _ACTIVE_HISTORICAL_CLAIMS.discard(self)
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()

    def __del__(self) -> None:
        self.close()


_ACTIVE_HISTORICAL_CLAIMS: set[_HistoricalReceiptClaim] = set()
_ACTIVE_HISTORICAL_CLAIMS_LOCK = Lock()


def main() -> None:
    from aegislm.artifacts import validate_artifact_path_plan
    from aegislm.tracking import (
        finish_active_wandb,
        git_reference,
        init_wandb_run,
        log_wandb_payload,
        require_wandb_api_key,
        update_wandb_summary,
        wandb_run_reference,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trainer-state",
        type=Path,
        default=Path(
            "checkpoints/source-v2-qlora/canary/checkpoint-125/trainer_state.json"
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("adapters/source-v2-qlora/canary/aegislm_training_manifest.json"),
    )
    parser.add_argument(
        "--gate-report",
        type=Path,
        default=Path("adapters/source-v2-qlora/canary/post_training_gate.json"),
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=Path("outputs/source-v2/wandb/historical-canary-import.json"),
    )
    parser.add_argument(
        "--wandb",
        action="store_true",
        help="Explicitly allow this command to contact W&B.",
    )
    parser.add_argument("--wandb-reconcile", choices=("retry-logging", "finish-only"))
    args = parser.parse_args()
    if not args.wandb:
        parser.error("historical import requires the explicit --wandb flag")
    validate_artifact_path_plan(
        inputs=(args.trainer_state, args.manifest, args.gate_report),
        outputs=(args.receipt,),
        protected_roots=(REPO_ROOT / "data", REPO_ROOT / "raw_datasets"),
        require_new=False,
    )
    require_wandb_api_key()

    trainer_state, trainer_state_sha256 = _load_object_with_sha256(args.trainer_state)
    manifest, manifest_sha256 = _load_object_with_sha256(args.manifest)
    gate, gate_report_sha256 = _load_object_with_sha256(args.gate_report)
    history_rows = _validated_history(trainer_state.get("log_history"))
    safe_manifest = _validated_manifest(manifest)
    safe_gate = _validated_gate(gate, safe_manifest)

    source_digests = {
        "trainer_state_sha256": trainer_state_sha256,
        "manifest_sha256": manifest_sha256,
        "gate_report_sha256": gate_report_sha256,
    }
    _require_frozen_source_digests(source_digests)
    identity = hashlib.sha256(
        json.dumps(source_digests, sort_keys=True).encode()
    ).hexdigest()[:12]
    run_id = f"source-v2-canary-import-{identity}"
    receipt_base = {
        "historical_import": True,
        "identity": identity,
        "source_digests": source_digests,
        "history_step_count": len(history_rows),
        "gate_passed": safe_gate["passed"],
    }
    receipt_claim = _prepare_receipt(
        args.receipt,
        receipt_base,
        ambiguous_resolution=args.wandb_reconcile,
    )
    if receipt_claim is None:
        print(f"historical canary W&B import already complete: run_id={run_id}")
        return

    if receipt_claim.needs_logging:
        _mark_logging_started(receipt_claim)
    run = init_wandb_run(
        job_type="historical-import",
        name="source-v2-canary-historical-2026-09-10",
        tags=("source-v2", "historical", "imported", "failed-canary"),
        run_id=run_id,
        resume=receipt_claim.resume,
        config={
            **source_digests,
            "stage": safe_manifest["stage"],
            "base_model_id": safe_manifest["base_model_id"],
            "base_model_revision": safe_manifest["base_model_revision"],
            "resolved_model_id": safe_manifest["resolved_model_id"],
            "resolved_model_revision": safe_manifest["resolved_model_revision"],
            "train_record_count": safe_manifest["train_record_count"],
            "validation_record_count": safe_manifest["validation_record_count"],
            "historical_import": True,
            "git": git_reference(REPO_ROOT),
        },
    )
    if receipt_claim.needs_logging:
        for row in history_rows:
            log_wandb_payload(
                run,
                {
                    "training/loss": row["loss"],
                    "training/learning_rate": row["learning_rate"],
                    "training/grad_norm": row["grad_norm"],
                    "training/epoch": row["epoch"],
                },
                step=row["step"],
            )
        update_wandb_summary(
            run,
            {
                "historical/imported_step_count": len(history_rows),
                "training/final_loss": safe_manifest["training_loss"],
                "training/elapsed_seconds": safe_manifest["elapsed_seconds"],
                "training/peak_vram_gb": safe_manifest["peak_vram_gb"],
                "gate/schema_pass_rate": safe_gate["schema_pass_rate"],
                "gate/minimum_schema_pass_rate": safe_gate["minimum_schema_pass_rate"],
                "gate/passed": safe_gate["passed"],
                "experiment/status": "failed_gate",
            },
        )
    reference = wandb_run_reference(run)
    if not isinstance(reference, dict):
        raise RuntimeError("W&B historical import run has no local reference")
    receipt = {**receipt_base, "status": "logged_pending_finish", "tracking": reference}
    _finish_with_receipt(receipt_claim, receipt, finish_active_wandb)
    print(
        "historical canary W&B import complete: "
        f"steps={len(history_rows)}, run_id={reference['run_id'] if reference else None}"
    )


def _load_object(path: Path) -> dict[str, Any]:
    value, _digest = _load_object_with_sha256(path)
    return value


def _load_object_with_sha256(path: Path) -> tuple[dict[str, Any], str]:
    from aegislm.artifacts import load_bounded_json_object

    try:
        return load_bounded_json_object(path, description=f"historical input {path}")
    except ValueError as exc:
        raise ValueError(f"{path}: invalid JSON") from exc


def _validated_history_row(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("trainer_state.log_history rows must be objects")
    step = value.get("step")
    if isinstance(step, bool) or not isinstance(step, int) or step <= 0:
        raise ValueError("trainer_state.log_history step must be a positive integer")
    return {
        "step": step,
        "loss": _finite_number(value.get("loss"), "history.loss", minimum=0.0),
        "learning_rate": _finite_number(
            value.get("learning_rate"), "history.learning_rate", minimum=0.0
        ),
        "grad_norm": _finite_number(
            value.get("grad_norm"), "history.grad_norm", minimum=0.0
        ),
        "epoch": _finite_number(value.get("epoch"), "history.epoch", minimum=0.0),
    }


def _validated_history(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("trainer_state.log_history must be a non-empty array")
    rows = [_validated_history_row(row) for row in value]
    if len(rows) != EXPECTED_HISTORY_STEPS:
        raise ValueError(
            f"historical trainer state must contain {EXPECTED_HISTORY_STEPS} steps"
        )
    if [row["step"] for row in rows] != list(range(1, len(rows) + 1)):
        raise ValueError(
            "trainer_state.log_history steps must be contiguous and monotonic from 1"
        )
    return rows


def _validated_manifest(value: dict[str, Any]) -> dict[str, Any]:
    expected_values = {
        "stage": "canary",
        "base_model_id": EXPECTED_BASE_MODEL_ID,
        "resolved_model_id": EXPECTED_RUNTIME_MODEL_ID,
        "resolved_model_revision": EXPECTED_RUNTIME_REVISION,
        "train_record_count": 1000,
        "validation_record_count": 40,
        "expert_adapter_tensors_present": True,
    }
    for key, expected in expected_values.items():
        if value.get(key) != expected or type(value.get(key)) is not type(expected):
            raise ValueError(f"historical manifest has unexpected {key}")
    base_revision = value.get("base_model_revision")
    if base_revision is not None and (
        not isinstance(base_revision, str)
        or re.fullmatch(r"[0-9a-f]{40}", base_revision) is None
    ):
        raise ValueError(
            "historical manifest base_model_revision must be null or 40 lowercase hex"
        )
    train_digest = _sha256(value.get("train_records_sha256"), "manifest digest")
    if train_digest != EXPECTED_TRAIN_RECORDS_SHA256:
        raise ValueError("historical manifest train digest is not the frozen canary")
    validated = {
        **expected_values,
        "base_model_revision": base_revision,
        "train_records_sha256": train_digest,
        "training_loss": _finite_number(
            value.get("training_loss"), "manifest.training_loss", minimum=0.0
        ),
        "elapsed_seconds": _finite_number(
            value.get("elapsed_seconds"), "manifest.elapsed_seconds", minimum=0.0
        ),
        "peak_vram_gb": _finite_number(
            value.get("peak_vram_gb"), "manifest.peak_vram_gb", minimum=0.0
        ),
    }
    return validated


def _validated_gate(value: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    if value.get("adapter_reload") is not True:
        raise ValueError("historical gate must confirm adapter_reload=true")
    if value.get("passed") is not False:
        raise ValueError("historical gate must be the preserved failed canary")
    if (
        isinstance(value.get("record_count"), bool)
        or not isinstance(value.get("record_count"), int)
        or value.get("record_count") != manifest["validation_record_count"]
    ):
        raise ValueError("historical gate record count does not match manifest")
    if value.get("runtime_model_id") != manifest["resolved_model_id"]:
        raise ValueError("historical gate runtime model does not match manifest")
    if value.get("runtime_model_revision") != manifest["resolved_model_revision"]:
        raise ValueError("historical gate runtime revision does not match manifest")
    if value.get("train_records_sha256") != manifest["train_records_sha256"]:
        raise ValueError("historical gate train digest does not match manifest")
    schema_rate = _finite_number(
        value.get("schema_pass_rate"), "gate.schema_pass_rate", minimum=0.0, maximum=1.0
    )
    threshold = _finite_number(
        value.get("minimum_schema_pass_rate"),
        "gate.minimum_schema_pass_rate",
        minimum=0.0,
        maximum=1.0,
    )
    if schema_rate >= threshold:
        raise ValueError("historical failed gate has a passing schema rate")
    validated = {
        "adapter_reload": True,
        "passed": False,
        "schema_pass_rate": schema_rate,
        "minimum_schema_pass_rate": threshold,
        "record_count": value["record_count"],
        "runtime_model_id": value["runtime_model_id"],
        "runtime_model_revision": value["runtime_model_revision"],
        "train_records_sha256": manifest["train_records_sha256"],
        "validation_records_sha256": _sha256(
            value.get("validation_records_sha256"), "gate validation digest"
        ),
        "config_sha256": _sha256(value.get("config_sha256"), "gate config digest"),
    }
    if validated["validation_records_sha256"] != EXPECTED_VALIDATION_RECORDS_SHA256:
        raise ValueError("historical gate validation digest is not the frozen canary")
    if validated["config_sha256"] != EXPECTED_GATE_CONFIG_SHA256:
        raise ValueError("historical gate config digest is not the frozen canary")
    return validated


def _finite_number(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    if minimum is not None and number < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{label} must be at most {maximum}")
    return number


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be 64 lowercase hex digits")
    return value


def _require_frozen_source_digests(source_digests: dict[str, str]) -> None:
    if source_digests != EXPECTED_SOURCE_DIGESTS:
        raise ValueError(
            "historical import source digests do not match the frozen canary"
        )


def _prepare_receipt(
    path: Path,
    base: dict[str, Any],
    *,
    ambiguous_resolution: str | None = None,
) -> _HistoricalReceiptClaim | None:
    from aegislm.artifacts import validate_artifact_output_location

    _validate_receipt_base(base)
    validate_artifact_output_location(path)
    stream = _acquire_receipt_claim_lock(path)
    try:
        if ambiguous_resolution is not None and not path.exists():
            raise ValueError(
                "historical W&B reconciliation requires an existing "
                "logging_ambiguous receipt"
            )
        if _create_pending_receipt_exclusive(path, {**base, "status": "pending"}):
            return _HistoricalReceiptClaim(path, "never", "pending", None, stream)
        existing = _load_object(path)
        _validate_receipt_state(existing)
        if any(existing.get(key) != value for key, value in base.items()):
            raise ValueError(
                "existing historical import receipt is for different inputs"
            )
        status = existing.get("status")
        if status == "complete":
            if ambiguous_resolution is not None:
                raise ValueError(
                    "historical W&B reconciliation requires logging_ambiguous state"
                )
            _release_lock_stream(stream)
            return None
        if status == "logging_ambiguous":
            if ambiguous_resolution is None:
                raise RuntimeError(
                    "historical W&B logging outcome is ambiguous; explicitly choose "
                    "--wandb-reconcile retry-logging or finish-only"
                )
            if ambiguous_resolution == "retry-logging":
                pending = {**base, "status": "pending"}
                _replace_receipt(path, pending)
                status = "pending"
            elif ambiguous_resolution != "finish-only":
                raise ValueError("invalid historical W&B reconciliation")
        elif ambiguous_resolution is not None:
            raise ValueError(
                "historical W&B reconciliation requires logging_ambiguous state"
            )
        if status not in {"pending", "logging_ambiguous", "logged_pending_finish"}:
            raise ValueError("existing historical import receipt has an invalid status")
        tracking = existing.get("tracking")
        return _HistoricalReceiptClaim(
            path,
            "allow",
            str(status),
            tracking if isinstance(tracking, dict) else None,
            stream,
        )
    except BaseException:
        _release_lock_stream(stream)
        raise


def _write_receipt(path: Path, value: dict[str, Any]) -> None:
    """Atomically replace the distinct historical-import receipt schema."""
    from aegislm.artifacts import validate_artifact_output_location

    _validate_receipt_state(value)
    validate_artifact_output_location(path)
    with _receipt_lock(path):
        if path.exists():
            existing = _load_object(path)
            _validate_receipt_state(existing)
            for key in (
                "historical_import",
                "identity",
                "source_digests",
                "history_step_count",
                "gate_passed",
            ):
                if existing.get(key) != value.get(key):
                    raise ValueError(
                        "existing historical import receipt is for different inputs"
                    )
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
                raise ValueError(
                    "historical import receipt status cannot move backwards"
                )
        _replace_receipt(path, value)


def _write_claimed_receipt(path: Path, value: dict[str, Any]) -> None:
    """Write while the historical-import claim remains exclusively held."""
    from aegislm.artifacts import validate_artifact_output_location

    _validate_receipt_state(value)
    validate_artifact_output_location(path)
    if path.exists():
        existing = _load_object(path)
        _validate_receipt_state(existing)
        for key in (
            "historical_import",
            "identity",
            "source_digests",
            "history_step_count",
            "gate_passed",
        ):
            if existing.get(key) != value.get(key):
                raise ValueError(
                    "existing historical import receipt is for different inputs"
                )
        status_order = {
            "pending": 0,
            "logging_ambiguous": 1,
            "logged_pending_finish": 2,
            "complete": 3,
        }
        if status_order[str(value["status"])] < status_order[str(existing["status"])]:
            raise ValueError("historical import receipt status cannot move backwards")
    _replace_receipt(path, value)


def _replace_receipt(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _create_pending_receipt_exclusive(path: Path, value: dict[str, Any]) -> bool:
    """Atomically publish historical pending state without a check/write race."""
    _validate_receipt_state(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".pending.tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            return False
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _finish_with_receipt(
    claim: _HistoricalReceiptClaim,
    receipt: dict[str, Any],
    finish: Callable[[int], None],
) -> None:
    if not isinstance(claim, _HistoricalReceiptClaim) or claim._stream is None:
        raise ValueError("an active historical import receipt claim is required")
    try:
        if claim.status not in {"logging_ambiguous", "logged_pending_finish"}:
            raise ValueError(
                "historical receipt must mark logging started before remote finish"
            )
        reference = receipt.get("tracking")
        if claim.tracking is not None and claim.tracking != reference:
            raise ValueError(
                "historical W&B recovery reference does not match the logged receipt"
            )
        _write_claimed_receipt(claim.path, receipt)
        finish(0)
        _write_claimed_receipt(claim.path, {**receipt, "status": "complete"})
    finally:
        claim.close()


def _mark_logging_started(claim: _HistoricalReceiptClaim) -> None:
    if not isinstance(claim, _HistoricalReceiptClaim) or claim._stream is None:
        raise ValueError("an active historical import receipt claim is required")
    if claim.status != "pending":
        raise ValueError("historical W&B logging can start only from pending state")
    _write_claimed_receipt(
        claim.path,
        {**_load_object(claim.path), "status": "logging_ambiguous"},
    )
    claim.status = "logging_ambiguous"


@contextmanager
def _receipt_lock(path: Path) -> Iterator[None]:
    from aegislm.artifacts import validate_artifact_output_location

    lock_path = path.with_name(f".{path.name}.lock")
    validate_artifact_output_location(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _acquire_receipt_claim_lock(path: Path) -> BinaryIO:
    from aegislm.artifacts import validate_artifact_output_location

    lock_path = path.with_name(f".{path.name}.lock")
    validate_artifact_output_location(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = lock_path.open("a+b")
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        stream.close()
        raise RuntimeError(
            "historical import receipt is already owned by another process"
        ) from exc
    return stream


def _release_lock_stream(stream: BinaryIO) -> None:
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        stream.close()


def _release_active_receipt_claims() -> None:
    with _ACTIVE_HISTORICAL_CLAIMS_LOCK:
        claims = tuple(_ACTIVE_HISTORICAL_CLAIMS)
    for claim in claims:
        claim.close()


def _validate_receipt_state(value: dict[str, Any]) -> None:
    _validate_receipt_base(value)
    identity = value["identity"]
    status = value.get("status")
    if status not in {
        "pending",
        "logging_ambiguous",
        "logged_pending_finish",
        "complete",
    }:
        raise ValueError("historical import receipt has an invalid status")
    tracking = value.get("tracking")
    if status in {"pending", "logging_ambiguous"}:
        if tracking is not None:
            raise ValueError("pre-log historical receipt must not contain tracking")
        return
    if not isinstance(tracking, dict):
        raise ValueError("completed historical receipt requires tracking linkage")
    for key in ("run_id", "run_url"):
        if not isinstance(tracking.get(key), str) or not tracking[key]:
            raise ValueError(f"historical receipt tracking requires {key}")
    expected_run_id = f"source-v2-canary-import-{identity}"
    if tracking["run_id"] != expected_run_id:
        raise ValueError("historical receipt tracking run ID is inconsistent")
    parsed = urlparse(tracking["run_url"])
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or expected_run_id not in parsed.path.split("/")
    ):
        raise ValueError("historical receipt tracking run URL is inconsistent")


def _validate_receipt_base(value: dict[str, Any]) -> None:
    if value.get("historical_import") is not True:
        raise ValueError("historical import receipt requires its schema marker")
    source_digests = value.get("source_digests")
    if not isinstance(source_digests, dict) or set(source_digests) != set(
        EXPECTED_SOURCE_DIGESTS
    ):
        raise ValueError("historical import receipt requires complete source digests")
    if any(
        not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None
        for digest in source_digests.values()
    ):
        raise ValueError("historical import receipt has an invalid source digest")
    expected_identity = hashlib.sha256(
        json.dumps(source_digests, sort_keys=True).encode()
    ).hexdigest()[:12]
    if value.get("identity") != expected_identity:
        raise ValueError("historical import receipt identity is inconsistent")
    if value.get("history_step_count") != EXPECTED_HISTORY_STEPS:
        raise ValueError("historical import receipt history count is inconsistent")
    if type(value.get("gate_passed")) is not bool:
        raise ValueError("historical import receipt gate status is invalid")


if __name__ == "__main__":
    from aegislm.tracking import finish_active_wandb

    try:
        main()
    except BaseException:
        try:
            finish_active_wandb(1)
        finally:
            _release_active_receipt_claims()
        raise
    else:
        try:
            finish_active_wandb(0)
        finally:
            _release_active_receipt_claims()
