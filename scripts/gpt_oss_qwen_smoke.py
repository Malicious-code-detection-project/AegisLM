"""Frozen Q1R10/Q1R11 five-step GPT-OSS smoke, with legacy evaluators."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
from typing import Any

import gpt_oss_pilot as pilot

OBJECTIVES = ("decision", "evidence")
FINAL_HEADER = "<|channel|>final<|message|>"


def bounded(config: dict[str, Any]) -> None:
    if config["max_steps"] != 5 or config["gradient_accumulation_steps"] != 32:
        raise ValueError("this smoke permits exactly five optimizer steps, accumulation 32")
    if not 0 < config["max_wall_seconds"] <= 3600 or config["gpu"] != 0:
        raise ValueError("smoke requires GPU 0 and at most 3600 seconds")
    if config["max_length"] != 4096 or config.get("full_training_approved", False):
        raise ValueError("unexpected sequence budget or full-training authorization")
    if config["generation_limits"] != {"decision": 128, "evidence": 512}:
        raise ValueError("generation budgets changed")


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def normalize_completion(raw: str) -> str:
    """Remove one terminal transport marker only; never repair model JSON."""
    value = raw.strip()
    marker = "<|return|>"
    if value.endswith(marker):
        return value[:-len(marker)].strip()
    return value


def validated_eos_id(tokenizer: Any) -> int:
    token_id = tokenizer.eos_token_id
    if type(token_id) is not int or token_id < 0 or tokenizer.eos_token != "<|return|>":
        raise ValueError("pinned GPT-OSS tokenizer requires a valid return EOS")
    return token_id


def prompt_ids(tokenizer: Any, messages: list[dict[str, Any]]) -> list[int]:
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, reasoning_effort="low")
    return tokenizer.encode(prompt + FINAL_HEADER, add_special_tokens=False)


def dataset_paths(config: dict[str, Any]) -> dict[str, Path]:
    root = Path(config["dataset_root"])
    defaults = {
        "decision_train": root / "phase-f-source-decision-v1/train.jsonl",
        "decision_validation": root / "phase-f-source-decision-v1/validation.jsonl",
        "evidence_train": root / "phase-f-source-evidence-lines-v1/canonical/train.jsonl",
        "evidence_challenge": root / "phase-f-source-evidence-lines-v1/development/challenge.jsonl",
        "evidence_gold": root / "phase-f-source-evidence-lines-v1/development/gold.jsonl",
        "evidence_private": root / "phase-f-source-evidence-lines-v1/development/private-records.jsonl",
    }
    return {key: Path(config.get("dataset_paths", {}).get(key, path)) for key, path in defaults.items()}


def groups(config: dict[str, Any]) -> tuple[dict[str, tuple[str, str]], list[Path]]:
    paths = [Path(p) for p in config["group_metadata"]]
    result: dict[str, tuple[str, str]] = {}
    for path in paths:
        if path.suffix == ".parquet":
            import pyarrow.parquet as pq
            rows = pq.read_table(path).to_pylist()
        else:
            rows = pilot.read_rows(path)
        for row in rows:
            record_id = row.get("record_id") or row.get("id")
            if row.get("record_id") and row.get("id") and row["record_id"] != row["id"]:
                raise ValueError("conflicting record identity")
            if not record_id or not row.get("group_id") or not row.get("code_sha256"):
                raise ValueError("missing group or code hash metadata")
            key = str(record_id)
            identity = (str(row["group_id"]), str(row["code_sha256"]))
            if key in result and result[key] != identity:
                raise ValueError("conflicting group or code hash metadata")
            result[key] = identity
    return result, paths


def verify(config: dict[str, Any], config_path: Path) -> dict[str, Any]:
    bounded(config)
    manifest = json.loads((Path(config["run_root"]) / "manifest.json").read_text())
    for name, expected in manifest["frozen_files"].items():
        if pilot.digest(Path(name)) != expected:
            raise RuntimeError(f"frozen input changed: {name}")
    if pilot.digest(config_path) != manifest["config_sha256"]:
        raise RuntimeError("config changed")
    pilot.verify_runtime(config)
    pilot.verify_snapshot(config)
    return manifest


def prepare(config: dict[str, Any], config_path: Path) -> None:
    from aegislm.datasets.source_decision import build_decision_development_subset

    bounded(config)
    pilot.verify_runtime(config)
    pilot.verify_snapshot(config)
    root = Path(config["run_root"])
    root.mkdir(parents=True, exist_ok=True)
    with (root / "PREPARE_STARTED").open("x") as handle:
        handle.write(time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    paths = dataset_paths(config)
    metadata, metadata_paths = groups(config)
    tokenizer = pilot.pilot_tokenizer(config)
    validated_eos_id(tokenizer)
    frozen = {str(p.resolve()): pilot.digest(p) for p in [*paths.values(), *metadata_paths, Path(__file__), Path(pilot.__file__), config_path]}
    package = Path(config["legacy_repo"]) / "aegislm"
    frozen.update({str(p.resolve()): pilot.digest(p) for p in package.rglob("*.py")})
    checksum_reports = {}
    source_roots = {paths["decision_train"].parent, paths["evidence_train"].parent.parent}
    for directory in {p.parent for p in paths.values()} | source_roots:
        for manifest_path in directory.glob("*manifest*.json"):
            frozen[str(manifest_path.resolve())] = pilot.digest(manifest_path)
        sums = directory / "SHA256SUMS"
        if directory in source_roots and not sums.exists():
            raise ValueError(f"missing source checksum manifest: {sums}")
        if sums.exists():
            count = 0
            for line in sums.read_text().splitlines():
                if not line.strip():
                    continue
                expected, filename = line.split(maxsplit=1)
                target = (directory / filename.lstrip(" *")).resolve()
                if directory.resolve() not in target.parents:
                    raise ValueError("unsafe checksum path")
                if pilot.digest(target) != expected:
                    raise ValueError(f"source checksum mismatch: {target}")
                frozen[str(target)] = expected
                count += 1
            frozen[str(sums.resolve())] = pilot.digest(sums)
            checksum_reports[str(directory)] = count
    stats = {}
    for objective in OBJECTIVES:
        target = root / objective
        target.mkdir()
        train = pilot.read_rows(paths[f"{objective}_train"])
        if objective == "decision":
            challenge, gold = build_decision_development_subset(pilot.read_rows(paths["decision_validation"]), per_class=50, seed=20260728)
        else:
            challenge, gold = [pilot.read_rows(paths[f"evidence_{kind}"]) for kind in ("challenge", "gold")]
            shutil.copyfile(paths["evidence_private"], target / "private-records.jsonl")
        train_ids, dev_ids = [{r["id"] for r in rows} for rows in (train, challenge)]
        if len(train_ids) != len(train) or len(dev_ids) != 100 or len(challenge) != 100 or len(gold) != 100 or {r["id"] for r in gold} != dev_ids:
            raise ValueError("duplicate IDs or incorrect development cohort")
        if (train_ids | dev_ids) - metadata.keys():
            raise ValueError("missing train/development provenance metadata")
        if train_ids & dev_ids or {metadata[i][0] for i in train_ids} & {metadata[i][0] for i in dev_ids}:
            raise ValueError("train/development ID or group leakage")
        if {metadata[i][1] for i in train_ids} & {metadata[i][1] for i in dev_ids}:
            raise ValueError("train/development exact code leakage")
        lengths = []
        for row in train:
            if [m["role"] for m in row["messages"]] != ["system", "user", "assistant"]:
                raise ValueError("unexpected training message roles")
            encoded = pilot.encode_record(tokenizer, row, config["max_length"])
            prefix = prompt_ids(tokenizer, row["messages"][:-1])
            if encoded["input_ids"][:len(prefix)] != prefix:
                raise ValueError("final-channel generation prefill differs from training prefix")
            if encoded["input_ids"][-1] != tokenizer.eos_token_id:
                raise ValueError("training target does not end in EOS")
            lengths.append(len(encoded["input_ids"]))
        prompt_lengths = []
        for row in challenge:
            if [m["role"] for m in row["messages"]] != ["system", "user"]:
                raise ValueError("challenge contains target or wrong roles")
            size = len(prompt_ids(tokenizer, row["messages"]))
            if size + config["generation_limits"][objective] > config["max_length"]:
                raise ValueError("generation sequence exceeds smoke budget")
            prompt_lengths.append(size)
        shutil.copyfile(paths[f"{objective}_train"], target / "train.jsonl")
        write_rows(target / "challenge.jsonl", challenge)
        write_rows(target / "gold.jsonl", gold)
        frozen.update({str(p.resolve()): pilot.digest(p) for p in target.glob("*.jsonl")})
        stats[objective] = {"train_count": len(train), "development_count": len(challenge), "max_train_tokens": max(lengths), "max_prompt_tokens": max(prompt_lengths), "id_overlap": 0, "group_overlap": 0, "exact_code_overlap": 0, "gold_assessment_conditioned": objective == "evidence"}
    manifest = {"config_sha256": pilot.digest(config_path), "frozen_files": frozen, "datasets": stats, "checksum_files_verified": checksum_reports, "max_steps_per_objective": 5, "end_to_end_evaluation": False}
    pilot.write_json(root / "manifest.json", manifest)
    print(json.dumps(stats), flush=True)


def evaluate(config: dict[str, Any], objective: str, phase: str) -> None:
    import torch
    from transformers import set_seed
    from aegislm.evaluation.harness import Prediction
    from aegislm.evaluation.source_decision import SourceDecisionThresholds, evaluate_source_decisions
    from aegislm.evaluation.source_evidence_lines import evaluate_source_evidence_predictions
    from aegislm.evaluation.source_two_stage import SourceTwoStageThresholds

    root = Path(config["run_root"]) / objective
    if phase == "reload":
        identities = json.loads((root / "adapter_hashes.json").read_text())
        for name, expected in identities.items():
            if pilot.digest(root / "adapter" / name) != expected:
                raise RuntimeError("saved adapter changed")
    set_seed(config["seed"])
    model, tokenizer = pilot.load_model(config, root / "adapter" if phase == "reload" else None)
    model.eval()
    model.config.use_cache = True
    torch.cuda.reset_peak_memory_stats()
    challenge, gold = [pilot.read_rows(root / f"{name}.jsonl") for name in ("challenge", "gold")]
    predictions, output = [], []
    start = time.monotonic()
    eos_ids = [validated_eos_id(tokenizer)]
    with (root / f"{phase}_predictions.jsonl").open("x", encoding="utf-8") as handle:
        for row in challenge:
            prompt = prompt_ids(tokenizer, row["messages"])
            ids = torch.tensor([prompt], device="cuda:0")
            tick = time.monotonic()
            with torch.inference_mode():
                generated = model.generate(input_ids=ids, attention_mask=torch.ones_like(ids), do_sample=False, max_new_tokens=config["generation_limits"][objective], pad_token_id=tokenizer.pad_token_id, eos_token_id=eos_ids, use_cache=True)
            tokens = generated[0, len(prompt):].tolist()
            raw = tokenizer.decode(tokens, skip_special_tokens=False)
            normalized = normalize_completion(raw)
            latency = 1000 * (time.monotonic() - tick)
            record = {"record_id": row["id"], "model_id": config["model_id"], "run_id": f"{config['experiment_id']}/{objective}/{phase}", "raw_output": normalized, "raw_decoded": raw, "token_ids": tokens, "eos_emitted": bool(tokens and tokens[-1] in eos_ids), "budget_exhausted": len(tokens) >= config["generation_limits"][objective] and not (tokens and tokens[-1] in eos_ids), "latency_ms": latency}
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            output.append(record)
            predictions.append(Prediction(record["record_id"], record["model_id"], record["run_id"], record["raw_output"], record["latency_ms"]))
            print(f"{objective}/{phase} {len(output)}/{len(challenge)}", flush=True)
    if objective == "decision":
        strict = asdict(SourceTwoStageThresholds())
        defaults = asdict(SourceDecisionThresholds())
        result = evaluate_source_decisions(gold, predictions, thresholds=SourceDecisionThresholds(**{key: strict[key] for key in defaults}))
    else:
        result = evaluate_source_evidence_predictions(challenge, gold, pilot.read_rows(root / "private-records.jsonl"), predictions)
    result["runtime"] = {"wall_seconds": time.monotonic() - start, "peak_allocated_gib": torch.cuda.max_memory_allocated() / 2**30, "peak_reserved_gib": torch.cuda.max_memory_reserved() / 2**30, "eos_count": sum(r["eos_emitted"] for r in output), "cap_count": sum(r["budget_exhausted"] for r in output)}
    pilot.write_json(root / f"{phase}_metrics.json", result)


def authorize(config: dict[str, Any], objective: str, phase: str) -> None:
    root = Path(config["run_root"])
    parent = json.loads((root / "RUN_STARTED").read_text())
    state = json.loads((root / "status.json").read_text())
    if parent["pid"] != os.getppid() or parent["nonce"] != os.environ.get("AEGISLM_SMOKE_NONCE") or state != {"status": "running", "objective": objective, "phase": phase}:
        raise RuntimeError("direct child execution is forbidden")
    with (root / objective / f"{phase.upper()}_STARTED").open("x") as handle:
        handle.write(parent["nonce"])


def run(config: dict[str, Any], config_path: Path) -> None:
    verify(config, config_path)
    pilot.verify_snapshot(config, weights=True)
    root = Path(config["run_root"])
    nonce = uuid.uuid4().hex
    with (root / "RUN_STARTED").open("x") as handle:
        json.dump({"pid": os.getpid(), "nonce": nonce}, handle)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="0", TOKENIZERS_PARALLELISM="false", HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1", WANDB_MODE="disabled", PYTHONUNBUFFERED="1", AEGISLM_SMOKE_NONCE=nonce)
    start = time.monotonic()
    try:
        for objective in OBJECTIVES:
            for phase in ("baseline", "train", "reload"):
                remaining = config["max_wall_seconds"] - (time.monotonic() - start)
                if remaining <= 0:
                    raise TimeoutError("aggregate smoke wall budget exhausted")
                pilot.write_json(root / "status.json", {"status": "running", "objective": objective, "phase": phase})
                with (root / objective / f"{phase}.log").open("x") as log:
                    subprocess.run([sys.executable, str(Path(__file__).resolve()), "--config", str(config_path.resolve()), "--phase", phase, "--objective", objective], env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=remaining)
        results = {objective: json.loads((root / objective / "reload_metrics.json").read_text()) for objective in OBJECTIVES}
        summary = {"technical_lifecycle": "PASS", "quality_gate": all(r["overall_pass"] for r in results.values()), "objectives": results, "end_to_end_evaluation": False, "steps_per_objective": 5, "wall_seconds": time.monotonic() - start, "additional_training_started": False}
        pilot.write_json(root / "summary.json", summary)
        pilot.write_json(root / "status.json", {"status": "completed"})
    except BaseException as error:
        pilot.write_json(root / "status.json", {"status": "failed", "error": str(error), "additional_training_started": False})
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--phase", choices=("prepare", "run", "baseline", "train", "reload"), required=True)
    parser.add_argument("--objective", choices=OBJECTIVES)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    sys.path.insert(0, config["legacy_repo"])
    if args.phase == "prepare":
        prepare(config, args.config)
    elif args.phase == "run":
        run(config, args.config)
    else:
        if args.objective is None:
            parser.error("child phases require --objective")
        verify(config, args.config)
        authorize(config, args.objective, args.phase)
        if args.phase == "train":
            stage = dict(config, run_root=str(Path(config["run_root"]) / args.objective))
            pilot.train(stage)
        else:
            evaluate(config, args.objective, args.phase)


if __name__ == "__main__":
    main()
