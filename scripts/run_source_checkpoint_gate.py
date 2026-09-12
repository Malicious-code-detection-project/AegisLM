"""Run an immutable source-v2 gate for a pinned base or saved checkpoint.

This command is diagnostic evidence only. Its report cannot authorize a full
training stage; canonical promotion still requires the recipe entrypoint's own
persisted-adapter gate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aegislm.environment import load_project_env  # noqa: E402

load_project_env(REPO_ROOT)

from aegislm.datasets import (  # noqa: E402
    load_source_records,
    records_sha256,
    select_stratified_canary,
)
from aegislm.training import (  # noqa: E402
    GenerationContract,
    create_exclusive_artifact_directory,
    file_sha256,
    load_source_training_config,
    run_source_schema_gate,
    source_protocol_config,
    source_protocol_sha256,
    source_training_config_sha256,
    source_training_recipe,
    validate_source_training_paths,
)


def main() -> None:
    from aegislm.artifacts import validate_artifact_path_plan, write_text_artifact
    from aegislm.inference.adapter import adapter_directory_sha256
    from aegislm.tracking import (
        build_tracking_receipt,
        finish_active_wandb,
        finish_with_tracking_receipt,
        git_reference,
        init_wandb_run,
        log_wandb_payload,
        mark_tracking_logging_started,
        prepare_tracking_receipt,
        require_wandb_api_key,
        source_training_wandb_config,
        tracking_payload_sha256,
        tracking_run_id,
        wandb_run_reference,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/source_v2_unsloth_v2.json")
    )
    role = parser.add_mutually_exclusive_group(required=True)
    role.add_argument("--base-only", action="store_true")
    role.add_argument("--adapter", type=Path)
    parser.add_argument(
        "--legacy-manifest",
        type=Path,
        help=(
            "Training manifest required only when a preserved checkpoint's "
            "adapter_config has no revision."
        ),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--wandb", action="store_true")
    parser.add_argument("--wandb-reconcile", choices=("retry-logging", "finish-only"))
    args = parser.parse_args()
    if args.wandb_reconcile and not args.wandb:
        parser.error("--wandb-reconcile requires --wandb")
    planned_inputs = [args.config]
    if args.adapter is not None:
        planned_inputs.append(args.adapter)
    if args.legacy_manifest is not None:
        planned_inputs.append(args.legacy_manifest)
    planned_outputs = [
        args.output_dir / "predictions.jsonl",
        args.output_dir / "diagnostic_report.json",
    ]
    validate_artifact_path_plan(
        inputs=planned_inputs,
        outputs=planned_outputs,
        protected_roots=(
            REPO_ROOT / "data",
            REPO_ROOT / "raw_datasets",
            REPO_ROOT / "models",
            REPO_ROOT / "adapters",
            REPO_ROOT / "checkpoints",
        ),
        require_new=False,
    )
    if args.wandb:
        require_wandb_api_key()
    if args.adapter is None and args.legacy_manifest is not None:
        parser.error("--legacy-manifest requires --adapter")
    if args.limit <= 0:
        raise ValueError("--limit must be positive")

    config = load_source_training_config(args.config)
    if source_training_recipe(config) not in {"unsloth_v2", "peft_split_control"}:
        raise ValueError("checkpoint diagnostics require an explicit non-legacy recipe")
    validate_source_training_paths(config)
    protocol = source_protocol_config(config)
    batch_size = args.batch_size or int(config["canary"]["generation_batch_size"])
    if batch_size <= 0:
        raise ValueError("--batch-size must be positive")
    all_records = load_source_records(
        Path(config["dataset"]["validation_path"]), require_assistant=True
    )
    records = select_stratified_canary(
        all_records,
        int(config["canary"]["validation_size"]),
        seed=int(config["training"]["seed"]),
    )[: args.limit]

    adapter_sha256 = None
    adapter_artifact_sha256 = None
    adapter_revision_source = None
    legacy_manifest_sha256 = None
    if args.adapter is not None:
        adapter_revision_source = _validate_adapter_config(
            args.adapter, config, legacy_manifest=args.legacy_manifest
        )
        adapter_sha256 = file_sha256(args.adapter / "adapter_model.safetensors")
        adapter_artifact_sha256 = adapter_directory_sha256(args.adapter)
        if args.legacy_manifest is not None:
            legacy_manifest_sha256 = file_sha256(args.legacy_manifest)
    forbidden_roots = [
        Path(config["training"]["output_dir"]),
        Path(config["training"]["checkpoint_dir"]),
        Path(config["model"]["cache_dir"]),
        Path(config["dataset"]["train_path"]).parent,
        Path(config["dataset"]["validation_path"]).parent,
        REPO_ROOT / "data",
        REPO_ROOT / "raw_datasets",
        REPO_ROOT / "models",
        REPO_ROOT / "adapters",
        REPO_ROOT / "checkpoints",
    ]
    if args.adapter is not None:
        forbidden_roots.append(args.adapter)
    run_role = "base" if args.base_only else "adapter"
    wandb_run = None
    wandb_claim = None
    receipt_path: Path | None = None
    receipt_base: dict[str, Any] | None = None
    if args.wandb:
        receipt_base = build_tracking_receipt(
            "gate",
            tracking_payload_sha256(
                {
                    "diagnostic_role": run_role,
                    "config_sha256": source_training_config_sha256(config),
                    "protocol_sha256": source_protocol_sha256(config),
                    "records_sha256": records_sha256(records),
                    "batch_size": batch_size,
                    "adapter_artifact_sha256": adapter_artifact_sha256,
                    "legacy_manifest_sha256": legacy_manifest_sha256,
                }
            ),
        )
        receipt_path = (
            REPO_ROOT
            / "outputs/source-v2/wandb"
            / f"{tracking_run_id(receipt_base)}.json"
        )
        wandb_claim = prepare_tracking_receipt(
            receipt_path,
            receipt_base,
            ambiguous_resolution=args.wandb_reconcile,
        )
        if wandb_claim is None:
            print("source-v2 checkpoint gate W&B receipt is already complete")
            return
        if not wandb_claim.needs_logging:
            safe_config = source_training_wandb_config(config, "canary", True)
            wandb_run = init_wandb_run(
                job_type="evaluation",
                name=f"source-v2-checkpoint-gate-{run_role}",
                tags=("source-v2", "checkpoint-diagnostic", run_role),
                config={
                    **safe_config,
                    "diagnostic_role": run_role,
                    "adapter_sha256": adapter_sha256,
                    "adapter_artifact_sha256": adapter_artifact_sha256,
                    "git": git_reference(REPO_ROOT),
                },
                run_id=tracking_run_id(receipt_base),
                resume=wandb_claim.resume,
            )
            reference = wandb_run_reference(wandb_run)
            if reference is None:
                raise RuntimeError("W&B recovery run has no local reference")
            finish_with_tracking_receipt(wandb_claim, reference, finish_active_wandb)
            print("source-v2 checkpoint gate W&B finish recovery complete")
            return
    validate_artifact_path_plan(
        inputs=planned_inputs,
        outputs=planned_outputs,
        protected_roots=(
            REPO_ROOT / "data",
            REPO_ROOT / "raw_datasets",
            REPO_ROOT / "models",
            REPO_ROOT / "adapters",
            REPO_ROOT / "checkpoints",
        ),
        require_new=True,
    )
    create_exclusive_artifact_directory(
        args.output_dir,
        forbidden_roots=tuple(forbidden_roots),
    )
    if args.wandb:
        assert receipt_base is not None
        assert wandb_claim is not None
        mark_tracking_logging_started(wandb_claim)
        safe_config = source_training_wandb_config(config, "canary", True)
        wandb_run = init_wandb_run(
            job_type="evaluation",
            name=f"source-v2-checkpoint-gate-{run_role}",
            tags=("source-v2", "checkpoint-diagnostic", run_role),
            config={
                **safe_config,
                "diagnostic_role": run_role,
                "adapter_sha256": adapter_sha256,
                "adapter_artifact_sha256": adapter_artifact_sha256,
                "git": git_reference(REPO_ROOT),
            },
            run_id=tracking_run_id(receipt_base),
            resume=wandb_claim.resume,
        )

    from unsloth import (  # type: ignore[import-not-found,import-untyped]
        FastLanguageModel,
    )
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required for checkpoint diagnostics")
    contract = GenerationContract(
        reasoning_effort=cast(Any, protocol["reasoning_effort"]),
        padding_side="left",
        pad_token_id=int(protocol["pad_token_id"]),
        eos_token_ids=tuple(protocol["eos_token_ids"]),
        do_sample=False,
        max_new_tokens=int(config["canary"]["max_new_tokens"]),
    )
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=config["model"]["runtime_model_id"],
        revision=config["model"]["revision"],
        max_seq_length=int(config["training"]["max_seq_length"]),
        dtype=None,
        load_in_4bit=True,
        cache_dir=config["model"]["cache_dir"],
    )
    resolved_id, resolved_revision = _resolved_model_identity(model, config)
    adapter_active = False
    tokenizer_contract_digest = None
    if args.adapter is not None:
        from peft import PeftModel  # type: ignore[import-not-found]
        from transformers import AutoTokenizer  # type: ignore[import-not-found]
        from aegislm.training.source import load_persisted_source_tokenizer

        model = PeftModel.from_pretrained(model, str(args.adapter), is_trainable=False)
        adapter_active = _has_active_adapter(model)
        if not adapter_active:
            raise RuntimeError("persisted adapter did not become active")
        tokenizer, tokenizer_contract_digest = load_persisted_source_tokenizer(
            AutoTokenizer, args.adapter, tokenizer, contract
        )
    FastLanguageModel.for_inference(model)

    summary = run_source_schema_gate(
        model=model,
        tokenizer=tokenizer,
        records=records,
        prediction_path=args.output_dir / "predictions.jsonl",
        batch_size=batch_size,
        contract=contract,
    )
    if (
        args.adapter is not None
        and adapter_directory_sha256(args.adapter) != adapter_artifact_sha256
    ):
        raise RuntimeError("adapter artifact changed during checkpoint diagnostics")
    report = {
        "schema_version": "aegislm.source-checkpoint-diagnostic.v1",
        "promotion_authority": False,
        "run_role": run_role,
        "source_recipe": source_training_recipe(config),
        "config_sha256": source_training_config_sha256(config),
        "protocol_sha256": source_protocol_sha256(config),
        "runtime_model_id": resolved_id,
        "runtime_model_revision": resolved_revision,
        "adapter_sha256": adapter_sha256,
        "adapter_artifact_sha256": adapter_artifact_sha256,
        "adapter_active": adapter_active,
        "tokenizer_contract_sha256": tokenizer_contract_digest,
        "adapter_revision_source": adapter_revision_source,
        "legacy_manifest_sha256": legacy_manifest_sha256,
        "record_count": summary.record_count,
        "records_sha256": records_sha256(records),
        "batch_size": batch_size,
        "passed_count": summary.passed_count,
        "schema_pass_rate": summary.schema_pass_rate,
        "parsed_count": summary.parsed_count,
        "harmony_prefix_count": summary.harmony_prefix_count,
        "harmony_final_count": summary.harmony_final_count,
        "finish_reasons": summary.finish_reasons,
        "tracking": wandb_run_reference(wandb_run),
    }
    write_text_artifact(
        args.output_dir / "diagnostic_report.json",
        json.dumps(report, indent=2, allow_nan=False) + "\n",
    )
    if wandb_run is not None:
        log_wandb_payload(
            wandb_run,
            {
                "gate/schema_pass_rate": summary.schema_pass_rate,
                "gate/passed_count": summary.passed_count,
                "gate/parsed_count": summary.parsed_count,
                "gate/harmony_prefix_count": summary.harmony_prefix_count,
                "gate/harmony_final_count": summary.harmony_final_count,
                **{
                    f"gate/finish_{key}": value
                    for key, value in summary.finish_reasons.items()
                },
            },
        )
        assert receipt_path is not None and receipt_base is not None
        reference = wandb_run_reference(wandb_run)
        if reference is None:
            raise RuntimeError("W&B checkpoint gate run has no local reference")
        assert wandb_claim is not None
        finish_with_tracking_receipt(wandb_claim, reference, finish_active_wandb)
    print(
        f"[OK] role={run_role} records={summary.record_count} "
        f"pass_rate={summary.schema_pass_rate:.3f}"
    )


def _validate_adapter_config(
    adapter_dir: Path,
    config: dict[str, Any],
    *,
    legacy_manifest: Path | None = None,
) -> str:
    config_path = adapter_dir / "adapter_config.json"
    weights_path = adapter_dir / "adapter_model.safetensors"
    if not config_path.is_file() or not weights_path.is_file():
        raise FileNotFoundError("adapter config or weights are missing")
    from aegislm.artifacts import load_bounded_json_object

    try:
        value, _digest = load_bounded_json_object(
            config_path, description="checkpoint adapter config"
        )
    except ValueError as exc:
        raise ValueError("adapter config is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("adapter config must be an object")
    if value.get("base_model_name_or_path") != config["model"]["runtime_model_id"]:
        raise ValueError("adapter base identity does not match the diagnostic config")
    if value.get("revision") == config["model"]["revision"]:
        return "adapter_config"
    if value.get("revision") is not None or legacy_manifest is None:
        raise ValueError("adapter base identity does not match the diagnostic config")
    _validate_legacy_checkpoint_manifest(adapter_dir, legacy_manifest, config)
    return "legacy_training_manifest"


def _validate_legacy_checkpoint_manifest(
    adapter_dir: Path, manifest_path: Path, config: dict[str, Any]
) -> None:
    from aegislm.artifacts import load_bounded_json_object

    try:
        manifest, _manifest_digest = load_bounded_json_object(
            manifest_path, description="legacy checkpoint manifest"
        )
        trainer_state, _trainer_state_digest = load_bounded_json_object(
            adapter_dir / "trainer_state.json",
            description="legacy checkpoint trainer state",
        )
    except ValueError as exc:
        raise ValueError("legacy checkpoint provenance is invalid") from exc
    if not isinstance(manifest, dict) or not isinstance(trainer_state, dict):
        raise ValueError("legacy checkpoint provenance is invalid")
    expected = config["model"]
    identity_matches = (
        manifest.get("base_model_id") == expected["base_model_id"]
        and manifest.get("resolved_model_id") == expected["runtime_model_id"]
        and manifest.get("resolved_model_revision") == expected["revision"]
    )
    step_text = adapter_dir.name.removeprefix("checkpoint-")
    step_matches = step_text.isdigit() and trainer_state.get("global_step") == int(
        step_text or -1
    )
    if not identity_matches or not step_matches:
        raise ValueError("legacy checkpoint provenance does not bind model and step")


def _resolved_model_identity(model: Any, config: dict[str, Any]) -> tuple[str, str]:
    resolved_id = str(getattr(model.config, "_name_or_path", ""))
    resolved_revision = getattr(model.config, "_commit_hash", None)
    if resolved_id != config["model"]["runtime_model_id"]:
        raise RuntimeError("resolved model identity does not match the config")
    if resolved_revision != config["model"]["revision"]:
        raise RuntimeError("resolved model revision does not match the config")
    return resolved_id, resolved_revision


def _has_active_adapter(model: Any) -> bool:
    active = getattr(model, "active_adapters", None)
    if callable(active):
        active = active()
    if active is None:
        active = getattr(model, "active_adapter", None)
    if isinstance(active, str):
        active_names = {active}
    elif isinstance(active, (list, tuple, set)):
        active_names = {str(item) for item in active}
    else:
        active_names = set()
    has_lora = any("lora_" in name for name, _ in model.named_parameters())
    return bool(active_names) and has_lora


if __name__ == "__main__":
    from aegislm.tracking import finish_active_wandb, release_active_tracking_claims

    try:
        main()
    except BaseException:
        try:
            finish_active_wandb(1)
        finally:
            release_active_tracking_claims()
        raise
    else:
        try:
            finish_active_wandb(0)
        finally:
            release_active_tracking_claims()
