"""Prepare only training records and frozen gold-free validation prompts."""

import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

import torch
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    config = json.loads((ROOT / "config.json").read_text())
    dataset = REPO / config["dataset_root"]
    assert digest(dataset / "manifest.json") == config["source_manifest_sha256"]
    assert digest(dataset / "split-audit.json") == config["split_audit_sha256"]
    assert json.loads((dataset / "split-audit.json").read_text())["pass"] is True
    train_path, validation_path = REPO / config["train_file"], REPO / config["validation_file"]
    assert digest(train_path) == config["train_file_sha256"]
    train, validation = read_jsonl(train_path), read_jsonl(validation_path)
    assert len(train) == 10000 and len(validation) == 1000
    train_ids, validation_ids = {r["id"] for r in train}, {r["id"] for r in validation}
    assert len(train_ids) == 10000 and len(validation_ids) == 1000 and train_ids.isdisjoint(validation_ids)
    # Verify the saved full split audit and ID separation without loading test content.
    assert json.loads((dataset / "manifest.json").read_text())["split_sizes"] == {"train": 10000, "validation": 1000, "test": 500}
    prompts, gold = json.loads((ROOT / "prompts.json").read_text()), json.loads((ROOT / "gold.json").read_text())
    assert [r["id"] for r in prompts] == config["generation"]["sample_ids"]
    validation_by_id = {r["id"]: r for r in validation}
    for row in prompts:
        assert row["id"] in validation_ids and row["id"] not in train_ids
        assert row["messages"] == validation_by_id[row["id"]]["messages"][:2]
        assert [m["role"] for m in row["messages"]] == ["system", "user"]
    for row in gold:
        assert row["expected_output"] == json.loads(validation_by_id[row["id"]]["messages"][-1]["content"])
    adapted = []
    for row in train:
        assert [m["role"] for m in row["messages"]] == ["system", "user", "assistant"]
        messages = [dict(m) for m in row["messages"]]
        assert set(json.loads(messages[-1]["content"])) == {"assessment"}
        assert json.loads(messages[-1]["content"])["assessment"] in {"present", "not_observed"}
        messages[-1]["thinking"] = ""
        assert all(a["content"] == b["content"] for a, b in zip(messages, row["messages"], strict=True))
        adapted.append({"id": row["id"], "messages": messages})
    path = ROOT / "training-messages.jsonl"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in adapted))
    snapshot = Path(config["hf_hub_cache"]) / "models--unsloth--gpt-oss-20b-unsloth-bnb-4bit/snapshots/093fba6992ef5a7152481afec0bdfca1ac486998"
    tokenizer = AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True)
    # Execute only the reviewed pure masking functions from the installed LGPLv3 Zoo source.
    zoo = Path(config["venv"]) / "lib/python3.12/site-packages/unsloth_zoo/dataset_utils.py"
    names = {"_longest_common_sublist", "_find_common_token_ids", "_stable_marker_edges", "train_on_responses_only"}
    nodes = [n for n in ast.parse(zoo.read_text()).body if
             (isinstance(n, ast.FunctionDef) and n.name in names) or
             (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_MARKER_EDGE_PROBES" for t in n.targets))]
    assert {n.name for n in nodes if isinstance(n, ast.FunctionDef)} == names
    namespace = {"torch": torch}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(zoo), "exec"), namespace)
    mask = namespace["train_on_responses_only"](
        None, tokenizer=tokenizer, return_function=True,
        instruction_part="<|start|>user<|message|>", response_part="<|start|>assistant<|channel|>final<|message|>",
    )
    records = []
    counts = Counter()
    for start in range(0, len(adapted), 128):
        batch = adapted[start:start + 128]
        texts = [tokenizer.apply_chat_template(r["messages"], tokenize=False, add_generation_prompt=False) for r in batch]
        assert all("<|start|>assistant<|channel|>final<|message|>" in text for text in texts)
        features = tokenizer(texts, add_special_tokens=False)
        truncated = [ids[:1024] for ids in features["input_ids"]]
        labels = mask({"input_ids": truncated})["labels"]
        for row, ids, labels_row in zip(batch, features["input_ids"], labels, strict=True):
            label = json.loads(row["messages"][-1]["content"])["assessment"]
            active = sum(value != -100 for value in labels_row)
            tail = tokenizer.encode(row["messages"][-1]["content"] + "<|return|>", add_special_tokens=False)
            complete = len(ids) <= 1024 and [value for value in labels_row if value != -100] == tail
            records.append({"id": row["id"], "tokens": len(ids), "supervised_tokens": active,
                            "complete_target": complete, "label": label})
            counts[f"{label}:all"] += 1
            counts[f"{label}:kept" if active else f"{label}:excluded"] += 1
            counts["overlength"] += len(ids) > 1024
            counts["complete_target"] += complete
            counts["partial_target"] += bool(active) and not complete
        print("Audited records", min(start + 128, len(adapted)), flush=True)
    report = {"status": "passed", "source_train_records": len(train), "source_validation_records": len(validation),
              "test_used": False, "train_validation_id_overlap": 0,
              "training_messages_sha256": digest(path), "pure_mask_source_sha256": digest(zoo),
              "counts": dict(counts), "records": records}
    (ROOT / "dataset-audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "records"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
