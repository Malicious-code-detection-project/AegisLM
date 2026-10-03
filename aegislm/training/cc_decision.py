"""Pinned provisional C/C++ decision inputs and preparation checks."""

from __future__ import annotations

from collections import Counter
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from aegislm.artifacts import (
    validate_artifact_output_location,
    validate_no_symlink_components,
)
from aegislm.datasets.source_corpus import (
    audit_splits,
    decision_messages,
    near_clone_pairs,
    sha,
)
from aegislm.environment import load_project_env
from aegislm.evaluation.harness import load_jsonl
from aegislm.training.fresh import resolve_fresh_tokenizer_snapshot
from aegislm.training.two_stage import (
    digest,
    freeze_tokenizer,
    tokenize_rows,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
SIZES = {"train": 10000, "validation": 1000, "test": 500}
TRAINING: dict[str, Any] = {
    "max_seq_length": 4096,
    "batch_size": 1,
    "gradient_accumulation_steps": 32,
    "max_steps": 100,
    "learning_rate": 1e-4,
    "warmup_ratio": 0.1,
    "lora_r": 8,
    "lora_alpha": 16,
    "lora_dropout": 0.05,
    "seed": 3407,
}


def package_versions() -> dict[str, str]:
    """Capture the libraries used by cached training and inference."""
    return {
        name: importlib.metadata.version(name)
        for name in (
            "torch",
            "transformers",
            "unsloth",
            "unsloth-zoo",
            "peft",
            "datasets",
            "wandb",
            "bitsandbytes",
            "triton",
            "accelerate",
            "tokenizers",
        )
    }


def tokenizer_fingerprint(tokenizer: Any) -> str:
    """Bind template/backend/special tokens, independent of the padding direction."""
    if tokenizer.pad_token_id != 200017 or not tokenizer.chat_template:
        raise ValueError("unexpected tokenizer contract")
    return sha(
        json.dumps(
            {
                "template": tokenizer.chat_template,
                "backend": json.loads(tokenizer.backend_tokenizer.to_str()),
                "special_tokens_map": tokenizer.special_tokens_map,
                "pad_token_id": tokenizer.pad_token_id,
                "eos_token_id": tokenizer.eos_token_id,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
    )


def tokenizer_assets(config: dict[str, Any]) -> dict[str, str]:
    """Hash cached tokenizer assets without importing a model runtime."""
    snapshot = resolve_fresh_tokenizer_snapshot(config)
    return {
        str(p): digest(p)
        for p in sorted(snapshot.iterdir())
        if p.is_file() and (p.suffix in {".json", ".jinja"})
    }


def gpu_identity() -> dict[str, str]:
    """Record local GPU conditions without initializing CUDA/Transformers."""
    rows = (
        subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,uuid,driver_version,memory.total",
                "--format=csv,noheader",
            ],
            text=True,
        )
        .strip()
        .splitlines()
    )
    if len(rows) != 1:
        raise ValueError("this comparison requires one visible physical GPU")
    name, uuid, driver, memory = [v.strip() for v in rows[0].split(",")]
    return {
        "name": name,
        "uuid": uuid,
        "driver": driver,
        "memory": memory,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", ""),
    }


def load_config(path: Path) -> dict[str, Any]:
    """Reject settings that the fixed runtime does not implement."""
    config: dict[str, Any] = json.loads(path.read_text())
    if os.environ.get("WORLD_SIZE", "1") != "1":
        raise ValueError("this fixed comparison requires world_size=1")
    if config["recipe"] != "cc_decision_v1" or config["training"] != TRAINING:
        raise ValueError("wrong recipe or unsupported training settings")
    if config.get("allow_unreviewed_source_labels") is not True:
        raise ValueError("explicit provisional-source-label experiment policy required")
    if config["protocol"] != {
        "template_date": "2026-10-02",
        "reasoning_effort": "low",
        "max_new_tokens": 128,
    }:
        raise ValueError("generation/template protocol is frozen")
    model = config["model"]
    if (model["base_model_id"], model["runtime_model_id"], model["revision"]) != (
        "openai/gpt-oss-20b",
        "unsloth/gpt-oss-20b-unsloth-bnb-4bit",
        "093fba6992ef5a7152481afec0bdfca1ac486998",
    ):
        raise ValueError("model identity/revision mismatch")
    dataset = Path(config["dataset"]["root"])
    if dataset.name != "cc-source-candidates-20260928-v5":
        raise ValueError("only the new v5 corpus is supported")
    if (
        config["dataset"]["manifest_sha256"],
        config["dataset"]["inventory_sha256"],
    ) != (
        "51db4812e9291a184d87818622ed8a5fc68542e75b9798cb36face961794c8f5",
        "ba729bf8e839d7ee4f90ad0ea0014d21f1dec1805ae936183c3bb901d2ff0d7e",
    ):
        raise ValueError("v5 release digests are frozen")
    validate_no_symlink_components(dataset, description="dataset")
    roots = [
        Path(config[key]).absolute()
        for key in ("output_dir", "adapter_dir", "checkpoint_dir")
    ]
    for output in roots:
        validate_artifact_output_location(output)
        if any(output.is_relative_to(other) for other in roots if other != output):
            raise ValueError("artifact roots must be disjoint")
    if len(set(roots)) != 3:
        raise ValueError("artifact roots must differ")
    return config


def verify_inputs(config: dict[str, Any]) -> dict[str, str]:
    """Check the pinned manifest, checksum inventory and all actual output files."""
    root = Path(config["dataset"]["root"])
    settings = config["dataset"]
    if (
        digest(root / "manifest.json") != settings["manifest_sha256"]
        or digest(root / "SHA256SUMS") != settings["inventory_sha256"]
    ):
        raise ValueError("v5 manifest/inventory digest mismatch")
    hashes = {"SHA256SUMS": settings["inventory_sha256"]}
    for line in (root / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split(maxsplit=1)
        path = root / name
        validate_no_symlink_components(path, description="dataset file")
        if (
            not path.resolve().is_relative_to(root.resolve())
            or digest(path) != expected
        ):
            raise ValueError(f"dataset checksum mismatch: {name}")
        hashes[name] = expected
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    if set(hashes) != actual:
        raise ValueError("dataset file inventory is incomplete")
    manifest = json.loads((root / "manifest.json").read_text())
    if (
        manifest["split_sizes"] != SIZES
        or manifest["approved_for_training"] is not False
        or manifest["evidence_training_records"] != 0
    ):
        raise ValueError("unexpected v5 size/review policy")
    return hashes


def validate_export(record: dict[str, Any], export: dict[str, Any], split: str) -> None:
    """Reject gold in challenge prompts or any canonical/export discrepancy."""
    if record["split"] != split or record["id"] != export["id"]:
        raise ValueError("record split/id mismatch")
    if export["messages"] != decision_messages(record, answer=split != "test"):
        raise ValueError("decision export disagrees with canonical record")
    annotation = record["annotation"]
    if (
        record["evidence_ranges"] is not None
        or annotation["approved_for_training"] is not False
        or annotation["decision_status"] != "source_label_unreviewed"
    ):
        raise ValueError("provisional annotation policy mismatch")


def load_data(config: dict[str, Any]) -> dict[str, Any]:
    """Load only the frozen v5 corpus; old source/evidence directories are irrelevant."""
    verify_inputs(config)
    root = Path(config["dataset"]["root"])
    canonical, exports = {}, {}
    for split, count in SIZES.items():
        rows = load_jsonl(root / "canonical" / f"{split}.jsonl")
        name = "challenge" if split == "test" else split
        messages = load_jsonl(root / "decision-candidates" / f"{name}.jsonl")
        if (
            len(rows) != count
            or len(messages) != count
            or len({r["id"] for r in rows}) != count
        ):
            raise ValueError(f"wrong {split} size or duplicate IDs")
        if Counter(r["assessment"] for r in rows) != {
            "present": count // 2,
            "not_observed": count // 2,
        }:
            raise ValueError("source label balance mismatch")
        for record, export in zip(rows, messages, strict=True):
            validate_export(record, export, split)
        canonical[split], exports[split] = rows, messages
    gold = load_jsonl(root / "decision-candidates/gold.jsonl")
    expected = [
        {
            "id": r["id"],
            "expected_output": {"assessment": r["assessment"]},
            "annotation_status": "source_label_unreviewed",
        }
        for r in canonical["test"]
    ]
    if gold != expected:
        raise ValueError("test gold/canonical disagreement")
    return {"canonical": canonical, "exports": exports, "test_gold": gold}


def development_rows(
    validation: list[dict[str, Any]], seed: int = 3407
) -> list[dict[str, Any]]:
    """Freeze a balanced 100-record subset from validation only."""
    selected = []
    for label in ("present", "not_observed"):
        rows = [
            r
            for r in validation
            if json.loads(r["messages"][-1]["content"])["assessment"] == label
        ]
        if len(rows) < 50:
            raise ValueError("insufficient validation development labels")
        selected.extend(sorted(rows, key=lambda r: sha(f"{seed}:dev:{r['id']}"))[:50])
    return sorted(selected, key=lambda r: sha(f"{seed}:dev-order:{r['id']}"))


def evaluation_rows(
    data: dict[str, Any], split: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return gold-free generation inputs and separate labels."""
    if split == "test":
        return data["exports"]["test"], data["test_gold"]
    rows = data["exports"]["validation"]
    if split == "development":
        rows = development_rows(rows)
    elif split != "validation":
        raise ValueError("evaluation split must be development/validation/test")
    prompts = [{"id": r["id"], "messages": r["messages"][:2]} for r in rows]
    gold = [
        {"id": r["id"], "expected_output": json.loads(r["messages"][-1]["content"])}
        for r in rows
    ]
    return prompts, gold


def wandb_readiness() -> dict[str, Any]:
    """Read authentication/project availability without creating or modifying a run."""
    load_project_env(ROOT)
    if not os.environ.get("WANDB_API_KEY", "").strip():
        return {
            "pass": False,
            "reason": "missing-WANDB_API_KEY",
            "remote_run_created": False,
        }
    try:
        api = importlib.import_module("wandb").Api(timeout=20)
        viewer = api.viewer
        entity = os.environ.get("WANDB_ENTITY") or api.default_entity
        project = api.project("aegislm", entity=entity)
        passed = bool(viewer and entity and project)
        return {
            "pass": passed,
            "credentials_configured": True,
            "authentication_confirmed": bool(viewer),
            "project_available": bool(project),
            "project": "aegislm",
            "remote_run_created": False,
        }
    except Exception as exc:
        return {
            "pass": False,
            "credentials_configured": True,
            "reason": type(exc).__name__,
            "remote_run_created": False,
        }


def prepare(config: dict[str, Any], path: Path) -> dict[str, Any]:
    """Perform CPU-only data/format preparation; never invoke a training worker."""
    output = Path(config["output_dir"])
    if output.exists():
        raise ValueError("preparation exists; do not overwrite it")
    data = load_data(config)
    rows = [r for split in SIZES for r in data["canonical"][split]]
    overlap = audit_splits(rows)
    overlap["near_clone_count"] = len(near_clone_pairs(rows))
    if not overlap["pass"] or overlap["near_clone_count"]:
        raise ValueError("actual canonical split isolation failed")
    tokenizer = importlib.import_module("transformers").AutoTokenizer.from_pretrained(
        str(resolve_fresh_tokenizer_snapshot(config)), local_files_only=True
    )
    date = config["protocol"]["template_date"]
    freeze_tokenizer(tokenizer, date, training=True)
    token_audit = {}
    extremes = []
    for split in SIZES:
        supervised_rows = [
            {"id": r["id"], "messages": decision_messages(r, answer=True)}
            for r in data["canonical"][split]
        ]
        features = tokenize_rows(supervised_rows, tokenizer, TRAINING["max_seq_length"])
        lengths = [len(f["input_ids"]) for f in features]
        counts = [sum(x != -100 for x in f["labels"]) for f in features]
        if min(counts) <= 0:
            raise ValueError("missing supervised labels")
        token_audit[split] = {
            "count": len(features),
            "min_tokens": min(lengths),
            "max_tokens": max(lengths),
            "min_supervised": min(counts),
            "max_supervised": max(counts),
        }
        if split == "train":
            extremes = [
                supervised_rows[lengths.index(min(lengths))]["id"],
                supervised_rows[lengths.index(max(lengths))]["id"],
            ]
    packages = package_versions()
    sources = sorted(set(ROOT.glob("aegislm/**/*.py")) | set(ROOT.glob("scripts/*.py")))
    manifest = {
        "recipe": config["recipe"],
        "config_sha256": digest(path),
        "date": date,
        "dataset_hashes": verify_inputs(config),
        "token_audit": token_audit,
        "split_audit": overlap,
        "development_ids": [
            r["id"] for r in development_rows(data["exports"]["validation"])
        ],
        "preflight_ids": extremes,
        "tokenizer_sha256": tokenizer_fingerprint(tokenizer),
        "tokenizer_assets": tokenizer_assets(config),
        "packages": packages,
        "source_hashes": {str(p.relative_to(ROOT)): digest(p) for p in sources},
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "sample_presentations": 3200,
        "train_pool_size": 10000,
        "full_epoch": False,
        "label_status": "source_label_unreviewed",
        "evidence_training": False,
        "production_approved": False,
        "optimizer_steps_started": 0,
        "pass": True,
    }
    write_json(output / "manifest.json", manifest)
    write_json(output / "config.json", config)
    return manifest


def context(config: dict[str, Any], path: Path) -> dict[str, Any]:
    """Block changed data, code or configuration after preparation."""
    manifest = json.loads((Path(config["output_dir"]) / "manifest.json").read_text())
    if digest(path) != manifest["config_sha256"]:
        raise ValueError("config changed after preparation")
    for name, expected in manifest["source_hashes"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"code changed after preparation: {name}")
    if package_versions() != manifest["packages"]:
        raise ValueError("runtime packages changed after preparation")
    if tokenizer_assets(config) != manifest["tokenizer_assets"]:
        raise ValueError("tokenizer assets changed after preparation")
    if verify_inputs(config) != manifest["dataset_hashes"]:
        raise ValueError("dataset changed after preparation")
    return manifest
