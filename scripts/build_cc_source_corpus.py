"""Build a local, provisional C/C++ corpus without inventing evidence labels.

Run with: uv run --group data-prep python scripts/build_cc_source_corpus.py
Raw code is never executed. Output is immutable, Git-ignored, and explicitly
blocked from production training until source-label and evidence review.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aegislm.artifacts import validate_artifact_output_location
from aegislm.datasets.source_corpus import (
    Components,
    audit_splits,
    clean_code,
    decision_messages,
    fingerprints,
    function_family,
    near_clone_pairs,
    normalize_project,
    normalize_record,
    sha,
    split_for_group,
    tokens,
)

SIZES = {"train": 10000, "validation": 1000, "test": 500}
EXTENSIONS = {".c", ".cc", ".cpp", ".cxx", ".c++", ".h", ".hpp", ".hh"}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dump(path: Path, value: Any) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def lines(path: Path) -> Iterator[dict[str, Any]]:
    with path.open() as stream:
        for line in stream:
            yield json.loads(line)


def walk(node: Any) -> Iterator[Any]:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def make_parsers() -> dict[str, Any]:
    from tree_sitter import Language, Parser
    import tree_sitter_c
    import tree_sitter_cpp

    return {
        "C": Parser(Language(tree_sitter_c.language())),
        "C++": Parser(Language(tree_sitter_cpp.language())),
    }


def parse_language(code: str, parsers: dict[str, Any]) -> str | None:
    data = code.encode()
    for language, parser in parsers.items():
        root = parser.parse(data).root_node
        functions = [node for node in walk(root) if node.type == "function_definition"]
        if not root.has_error and len(functions) == 1:
            return language
    return None


def source_rows(
    raw: Path, processed: Path, inventory: dict[str, Any], inputs: set[Path]
) -> Iterator[dict[str, Any]]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    for path in sorted((raw / "primevul/v0.1").glob("primevul_*.jsonl")):
        # Paired files are alternate views of the main records, not extra samples.
        if "paired" in path.name:
            continue
        inputs.add(path)
        for index, row in enumerate(lines(path)):
            yield dict(
                dataset="primevul",
                original_id=str(row["idx"]),
                code=row["func"],
                label=row["target"],
                cwes=row.get("cwe", []),
                project=row["project"],
                commit=row.get("commit_id", ""),
                cves=row.get("cve", ""),
                file=row.get("file_name", ""),
                language="C/C++",
                input_file=str(path),
                input_row=index + 1,
            )
    for path in sorted((raw / "diversevul/data").glob("*.parquet")):
        inputs.add(path)
        index = 0
        for batch in pq.ParquetFile(path).iter_batches(batch_size=2048):
            for row in batch.to_pylist():
                index += 1
                yield dict(
                    dataset="diversevul",
                    original_id=f"{path.name}:{index}",
                    code=row["func"],
                    label=row["target"],
                    cwes=row.get("cwe", []),
                    project=row["project"],
                    commit=row.get("commit_id", ""),
                    cves="",
                    file="",
                    language="C/C++",
                    input_file=str(path),
                    input_row=index,
                )
    csv.field_size_limit(128 * 1024 * 1024)
    for path in sorted((raw / "bigvul").glob("*.csv")):
        inputs.add(path)
        with path.open(newline="") as stream:
            for index, row in enumerate(csv.DictReader(stream)):
                language = row.get("lang", "").lower()
                if language not in {"c", "c++", "cpp"}:
                    inventory["bigvul_non_cc"] += 1
                    continue
                common = dict(
                    dataset="bigvul",
                    cwes=row.get("CWE ID", ""),
                    project=row.get("project", ""),
                    commit=row.get("commit_id", ""),
                    cves=row.get("CVE ID", ""),
                    file=row.get("file_name", ""),
                    language="C/C++",
                    input_file=str(path),
                    input_row=index + 2,
                )
                yield dict(
                    common,
                    original_id=f"{path.name}:{index}:before",
                    code=row["func_before"],
                    label=int(row["vul"]),
                )
                if (
                    row["func_after"].strip()
                    and row["func_after"] != row["func_before"]
                ):
                    # A changed function is not automatically a verified negative.
                    yield dict(
                        common,
                        original_id=f"{path.name}:{index}:after",
                        code=row["func_after"],
                        label=None,
                    )
    parsers = make_parsers()
    juliet_root = raw / "sard-juliet-c-cpp-1.3"
    for path in sorted(juliet_root.rglob("*")):
        if path.suffix not in {".c", ".cpp"} or not re.search(r"CWE\d+_", path.name):
            continue
        inputs.add(path)
        content = path.read_bytes()
        language = "C" if path.suffix == ".c" else "C++"
        root = parsers[language].parse(content).root_node
        family = re.sub(r"_\d+[a-z]?$", "", path.stem)
        for node in walk(root):
            if node.type != "function_definition":
                continue
            declaration = node.child_by_field_name("declarator")
            if declaration is None:
                continue
            identifiers = [
                n
                for n in walk(declaration)
                if n.type in {"identifier", "field_identifier"}
            ]
            if not identifiers:
                continue
            name = content[identifiers[0].start_byte : identifiers[0].end_byte].decode(
                errors="replace"
            )
            label = (
                1
                if re.search(r"(?:^|_)bad$", name)
                else 0
                if re.search(r"(?:^|_)good", name)
                else None
            )
            yield dict(
                dataset="juliet",
                original_id=f"{path.relative_to(juliet_root)}:{node.start_byte}",
                code=content[node.start_byte : node.end_byte].decode(errors="replace"),
                label=label,
                cwes=re.findall(r"CWE\d+", path.name)[0].replace("CWE", "CWE-"),
                project=f"juliet:{family}",
                commit="",
                cves="",
                file=str(path.relative_to(juliet_root)),
                language=language,
                input_file=str(path),
                input_row=node.start_point.row + 1,
            )
    for path in sorted((raw / "decompile-bench").glob("*/*.arrow")):
        inputs.add(path)
        with pa.memory_map(str(path), "r") as stream:
            index = 0
            for batch in pa.ipc.open_stream(stream):
                for row in batch.to_pylist():
                    index += 1
                    if Path(row["file"]).suffix.lower() not in EXTENSIONS:
                        inventory["decompile_non_cc_or_unknown"] += 1
                        continue
                    yield dict(
                        dataset="decompile-bench",
                        original_id=str(index),
                        code=row["code"],
                        label=None,
                        cwes=[],
                        project=row["file"].split("/")[1],
                        commit="",
                        cves="",
                        file=row["file"],
                        language="C/C++",
                        input_file=str(path),
                        input_row=index,
                    )
    # Use the already-imported read-only SQLite cache; record and verify its digest.
    db_path = processed / "phase-f-cvefixes-v1.0.8/CVEfixes.db"
    report_path = db_path.parent / "import-report.json"
    if not db_path.is_file():
        inventory["cvefixes"] = {
            "disposition": "pending_sql_import",
            "reason": "no SQLite cache",
        }
        return
    expected = json.loads(report_path.read_text())["database"]["sha256"]
    actual = digest(db_path)
    if actual != expected:
        raise ValueError("CVEfixes imported database hash mismatch")
    inputs.update([db_path, report_path])
    inventory["cvefixes_cache_sha256"] = actual
    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    fixes: dict[str, list[str]] = defaultdict(list)
    for cve, commit in conn.execute("SELECT cve_id, hash FROM fixes"):
        fixes[commit].append(cve)
    cwes: dict[str, list[str]] = defaultdict(list)
    for cve, cwe in conn.execute("SELECT cve_id,cwe_id FROM cwe_classification"):
        cwes[cve].append(cwe)
    repositories = dict(conn.execute("SELECT hash,repo_url FROM commits"))
    files = {}
    for file_id, commit, name, language in conn.execute(
        "SELECT file_change_id,hash,filename,programming_language FROM file_change"
    ):
        if language.lower() in {"c", "c++", "cpp"}:
            files[file_id] = (commit, name, language)
    for method_id, file_id, code, before in conn.execute(
        "SELECT method_change_id,file_change_id,code,before_change FROM method_change"
    ):
        if file_id not in files:
            continue
        commit, name, language = files[file_id]
        yield dict(
            dataset="cvefixes",
            original_id=method_id,
            code=code,
            label=None,
            cwes=[cwe for cve in fixes[commit] for cwe in cwes[cve]],
            project=repositories.get(commit, ""),
            commit=commit,
            cves=fixes[commit],
            file=name,
            language=language,
            input_file=str(db_path),
            input_row=method_id,
            before_change=before,
        )
    conn.close()


def historical_fingerprints(processed: Path, inventory: dict[str, Any]) -> set[str]:
    protected: set[str] = set()
    seen: set[str] = set()
    inputs = []
    for directory in sorted(processed.glob("phase-f-source-*")):
        for name in [
            "train.jsonl",
            "validation.jsonl",
            "challenge.jsonl",
            "canonical/train.jsonl",
            "canonical/validation.jsonl",
        ]:
            path = directory / name
            if not path.is_file():
                continue
            count = 0
            for row in lines(path):
                messages = row.get("messages", [])
                for message in messages:
                    if message.get("role") != "user":
                        continue
                    content = message["content"]
                    if "{" not in content:
                        continue
                    try:
                        payload, _ = json.JSONDecoder().raw_decode(
                            content[content.index("{") :]
                        )
                    except ValueError:
                        continue
                    code = payload.get("source_code")
                    if code is None and "numbered_source_code" in payload:
                        code = re.sub(
                            r"^\d+\|",
                            "",
                            payload["numbered_source_code"],
                            flags=re.MULTILINE,
                        )
                    if not isinstance(code, str):
                        continue
                    count += 1
                    if sha(code) in seen:
                        continue
                    seen.add(sha(code))
                    protected.update(fingerprints(clean_code(code))[1:])
            inputs.append(
                {"path": str(path), "sha256": digest(path), "source_records": count}
            )
    inventory["historical_inputs"] = inputs
    inventory["historical_unique_source_count"] = len(seen)
    return protected


def metadata_inventory(raw: Path) -> dict[str, Any]:
    import duckdb

    report: dict[str, Any] = {"bigvul_non_cc": 0, "decompile_non_cc_or_unknown": 0}
    path = next((raw / "assemblage").glob("*/*.duckdb"))
    conn = duckdb.connect(
        str(path),
        read_only=True,
        config={
            "enable_external_access": "false",
            "threads": "2",
            "memory_limit": "1GB",
        },
    )
    total, nonempty = conn.execute(
        "SELECT count(*),count(*) FILTER(WHERE source_codes IS NOT NULL AND length(trim(source_codes))>0) FROM functions"
    ).fetchone()
    conn.close()
    report["assemblage"] = {
        "path": str(path),
        "functions": total,
        "nonempty_function_source": nonempty,
        "disposition": "excluded_no_complete_function_source_or_labels",
        "limitation": "line-level reconstruction not attempted",
    }
    if nonempty:
        raise ValueError("Assemblage contains source: explicit importer is required")
    path = raw / "arvo/v3.0.0/arvo.db"
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    report["arvo"] = {
        "path": str(path),
        "languages": conn.execute(
            "SELECT language,count(*) FROM arvo GROUP BY language"
        ).fetchall(),
        "disposition": "excluded_metadata_only_no_function_source",
    }
    conn.close()
    report["cybersecurity-qa-v2"] = {
        "disposition": "excluded_chat_corpus_no_function_level_labels"
    }
    report["ember2024"] = {"disposition": "excluded_binary_features_not_cc_source"}
    report["ember2024-benchmark-models"] = {"disposition": "excluded_model_not_dataset"}
    return report


def build(
    raw: Path,
    processed: Path,
    output: Path,
    seed: int,
    reuse_pool: Path | None = None,
    exclude_ids: Path | None = None,
) -> None:
    validate_artifact_output_location(output)
    output.mkdir(parents=True, exist_ok=False)
    if reuse_pool is not None:
        if (reuse_pool / "index.sqlite-journal").exists():
            raise ValueError("Refuse a pool with an active SQLite journal")
        pool = reuse_pool / "pool"
        inventory = json.loads((reuse_pool / "inventory.json").read_text())
        stats = Counter(
            json.loads((reuse_pool / "normalization_counts.json").read_text())
        )
        protected = historical_fingerprints(processed, inventory)
        db = sqlite3.connect(
            f"file:{(reuse_pool / 'index.sqlite').resolve()}?mode=ro", uri=True
        )
        handles = {path.stem: None for path in pool.glob("*.jsonl")}
        inputs = set(pool.glob("*.jsonl")) | {reuse_pool / "index.sqlite"}
        expected_rows = sum(v for k, v in stats.items() if k.endswith(":normalized"))
        if db.execute("SELECT count(*) FROM records").fetchone()[0] != expected_rows:
            raise ValueError("Incomplete normalized pool")
        dump(output / "inventory.json", inventory)
        dump(output / "normalization_counts.json", dict(stats))
    else:
        pool = output / "pool"
        pool.mkdir()
        inventory = metadata_inventory(raw)
        protected = historical_fingerprints(processed, inventory)
        print(
            f"Historical distinct code: {inventory['historical_unique_source_count']}",
            flush=True,
        )
        inputs: set[Path] = set()
        db = sqlite3.connect(output / "index.sqlite")
        db.execute(
            "CREATE TABLE records(id TEXT PRIMARY KEY,dataset TEXT,offset INTEGER,length INTEGER,lexical TEXT,abstract TEXT,project TEXT,commit_id TEXT,cves TEXT,label TEXT,cwe TEXT,eligible INTEGER)"
        )
        stats: Counter[str] = Counter()
        handles: dict[str, Any] = {}
        for raw_row in source_rows(raw, processed, inventory, inputs):
            row = normalize_record(raw_row)
            if row is None:
                stats[raw_row["dataset"] + ":empty"] += 1
                continue
            dataset = raw_row["dataset"]
            if dataset not in handles:
                handles[dataset] = (pool / f"{dataset}.jsonl").open("xb")
            stream = handles[dataset]
            offset = stream.tell()
            encoded = (json.dumps(row, ensure_ascii=False) + "\n").encode()
            stream.write(encoded)
            project = normalize_project(raw_row["project"])
            ts = tokens(row["source_code"])
            eligible = bool(
                row["assessment"]
                and row["target_cwe"]
                and project
                and 25 <= len(ts) <= 1800
                and len(row["source_code"]) <= 18000
                and "{" in ts
                and "}" in ts
            )
            db.execute(
                "INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["id"],
                    dataset,
                    offset,
                    len(encoded),
                    row["hashes"]["lexical"],
                    row["hashes"]["abstract"],
                    project,
                    str(raw_row["commit"] or ""),
                    json.dumps(raw_row["cves"]),
                    row["assessment"],
                    row["target_cwe"],
                    int(eligible),
                ),
            )
            stats[dataset + ":normalized"] += 1
            stats[dataset + ":preeligible"] += int(eligible)
            if (
                sum(v for k, v in stats.items() if k.endswith(":normalized")) % 25000
                == 0
            ):
                db.commit()
                print(dict(stats), flush=True)
        for stream in handles.values():
            stream.close()
        db.commit()
        dump(output / "inventory.json", inventory)
        dump(output / "normalization_counts.json", dict(stats))
    components = Components()
    if "cvefixes" in handles:
        inputs.add(processed / "phase-f-cvefixes-v1.0.8/import-report.json")
    # All rows contribute provenance and duplicate edges, including unselected
    # before/after versions and unlabeled functions that bridge source datasets.
    for path in sorted(pool.glob("*.jsonl")):
        for row in lines(path):
            provenance = row["provenance"]
            inputs.add(Path(provenance["input_file"]))
            project = normalize_project(provenance["project"])
            keys = ["row:" + row["id"]]
            # Trivial empty stubs must not connect unrelated projects. All
            # selectable functions have >=25 tokens and retain clone edges.
            if len(tokens(row["source_code"])) >= 25:
                keys.extend(
                    [
                        "lex:" + row["hashes"]["lexical"],
                        "abs:" + row["hashes"]["abstract"],
                    ]
                )
            if provenance["dataset"] == "juliet":
                keys.append("juliet-family:" + project)
            else:
                family = function_family(row["source_code"])
                if project and family:
                    keys.append(f"function:{project}:{family}")
            if provenance["commit"]:
                keys.append("commit:" + provenance["commit"])
            keys.extend(
                "cve:" + cve
                for cve in re.findall(r"CVE-\d{4}-\d+", json.dumps(provenance["cves"]))
            )
            components.union(keys)
    blocked_roots = {
        components.find(prefix + value)
        for value in protected
        for prefix in ["lex:", "abs:"]
        if prefix + value in components.parent
    }
    conflict_hashes = {
        r[0]
        for r in db.execute(
            "SELECT lexical FROM records WHERE label IS NOT NULL GROUP BY lexical HAVING count(DISTINCT label)>1"
        )
    }
    candidates = list(
        db.execute(
            "SELECT id,dataset,offset,length,lexical,abstract,label FROM records WHERE eligible=1 ORDER BY id"
        )
    )
    print(
        f"Preeligible candidates: {len(candidates)}; conflicting lexical hashes: {len(conflict_hashes)}",
        flush=True,
    )
    parsers = make_parsers()
    reads = {dataset: (pool / f"{dataset}.jsonl").open("rb") for dataset in handles}
    initial_excluded: set[str] = set()
    if exclude_ids is not None:
        values = json.loads(exclude_ids.read_text())
        if not isinstance(values, list) or not all(
            isinstance(value, str) for value in values
        ):
            raise ValueError("Exclusions must be a JSON array of record IDs")
        initial_excluded = set(values)
        if not initial_excluded.issubset({item[0] for item in candidates}):
            raise ValueError("Exclusion IDs are not selectable pool records")
        inputs.add(exclude_ids)
    excluded: set[str] = set(initial_excluded)
    cached: dict[str, dict[str, Any]] = {}
    rounds = []
    for iteration in range(100):
        blocked = {components.find(group) for group in blocked_roots}
        buckets: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
        duplicate: set[str] = set()
        # Prefer PrimeVul when identical source annotations agree; do not count
        # alternative dataset views as independent samples.
        priority = {"primevul": 0, "diversevul": 1, "bigvul": 2, "juliet": 3}
        for item in sorted(
            candidates, key=lambda x: (priority[x[1]], sha(f"{seed}:{x[0]}"))
        ):
            record_id, dataset, _, _, lexical, abstract, label = item
            group = components.find("lex:" + lexical)
            if (
                record_id in excluded
                or group in blocked
                or lexical in conflict_hashes
                or lexical in duplicate
            ):
                continue
            duplicate.add(lexical)
            split = split_for_group(group, seed)
            buckets[split, label, dataset].append((item, group))
        selected = []
        selected_ids: set[str] = set()
        owners: dict[str, str] = {}
        parse_rejected = 0
        for split, count in SIZES.items():
            for label in ["present", "not_observed"]:
                needed = count // 2
                supplies = {
                    dataset: list(reversed(buckets[split, label, dataset]))
                    for dataset in priority
                }
                taken = 0
                fallback = False
                while taken < needed:
                    progress = False
                    for dataset in priority:
                        if taken >= needed:
                            break
                        if not supplies[dataset]:
                            continue
                        item, group = supplies[dataset].pop()
                        record_id, _, offset, length, *_ = item
                        if (
                            record_id in selected_ids
                            or record_id in excluded
                            or owners.get(group, split) != split
                        ):
                            progress = True
                            continue
                        row = cached.get(record_id)
                        if row is None:
                            stream = reads[dataset]
                            stream.seek(offset)
                            row = json.loads(stream.read(length))
                            language = parse_language(row["source_code"], parsers)
                            if language is None:
                                excluded.add(record_id)
                                parse_rejected += 1
                                progress = True
                                continue
                            row["language"] = language
                            cached[record_id] = row
                        row = dict(
                            row, split=split, group_id="group-" + sha(group)[:24]
                        )
                        selected.append(row)
                        selected_ids.add(record_id)
                        owners[group] = split
                        taken += 1
                        progress = True
                    if not progress:
                        if not fallback:
                            # A hash bucket can run short after parsing or
                            # exclusions. Allocate only previously unused whole
                            # groups; never move a group already in another split.
                            supplies = {
                                dataset: sorted(
                                    [
                                        entry
                                        for other in SIZES
                                        for entry in buckets[other, label, dataset]
                                    ],
                                    key=lambda entry: sha(
                                        f"{seed}:reserve:{entry[0][0]}"
                                    ),
                                    reverse=True,
                                )
                                for dataset in priority
                            }
                            fallback = True
                            continue
                        raise ValueError(
                            f"Insufficient {split}/{label}: {taken}/{needed}; do not relax gates"
                        )
        pairs = near_clone_pairs(selected)
        rounds.append(
            {
                "iteration": iteration,
                "cross_split_near_clone_pairs": len(pairs),
                "parse_rejected": parse_rejected,
                "reserve_groups_allocated": sum(
                    split_for_group(group, seed) != split
                    for group, split in owners.items()
                ),
            }
        )
        print(rounds[-1], flush=True)
        if not pairs:
            break
        for a, b in pairs:
            components.union(
                [
                    "lex:" + selected[a]["hashes"]["lexical"],
                    "lex:" + selected[b]["hashes"]["lexical"],
                ]
            )
    else:
        raise ValueError("Near-clone grouping did not converge")
    for stream in reads.values():
        stream.close()
    final_audit = audit_splits(selected)
    if not final_audit["pass"]:
        raise ValueError(f"Final split leakage: {final_audit}")
    for directory in ["canonical", "decision-candidates", "review"]:
        (output / directory).mkdir()
    for split, count in SIZES.items():
        rows = sorted(
            (row for row in selected if row["split"] == split),
            key=lambda row: sha(f"{seed}:output:{row['id']}"),
        )
        assert len(rows) == count
        with (output / "canonical" / f"{split}.jsonl").open("x") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        with (
            output
            / "decision-candidates"
            / ("challenge.jsonl" if split == "test" else f"{split}.jsonl")
        ).open("x") as stream:
            for row in rows:
                stream.write(
                    json.dumps(
                        {
                            "id": row["id"],
                            "messages": decision_messages(row, answer=split != "test"),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        if split == "test":
            with (output / "decision-candidates/gold.jsonl").open("x") as stream:
                for row in rows:
                    stream.write(
                        json.dumps(
                            {
                                "id": row["id"],
                                "expected_output": {"assessment": row["assessment"]},
                                "annotation_status": "source_label_unreviewed",
                            }
                        )
                        + "\n"
                    )
    with (output / "review/evidence-pending.jsonl").open("x") as stream:
        for row in selected:
            stream.write(
                json.dumps(
                    {
                        "id": row["id"],
                        "split": row["split"],
                        "decision_status": row["annotation"]["decision_status"],
                        "evidence_status": "unreviewed",
                        "evidence_ranges": None,
                    }
                )
                + "\n"
            )
    # Re-read the actual emitted files. Never audit only an earlier in-memory pool.
    final_rows = [
        row for split in SIZES for row in lines(output / "canonical" / f"{split}.jsonl")
    ]
    emitted = audit_splits(final_rows)
    emitted["cross_split_near_clone_pairs"] = len(near_clone_pairs(final_rows))
    emitted["historical_fingerprint_matches"] = sum(
        any(value in protected for value in fingerprints(row["source_code"])[1:])
        for row in final_rows
    )
    emitted["pass"] = (
        emitted["pass"]
        and emitted["cross_split_near_clone_pairs"] == 0
        and emitted["historical_fingerprint_matches"] == 0
    )
    if not emitted["pass"]:
        raise ValueError(f"Emitted artifact audit failed: {emitted}")
    dump(
        output / "split-audit.json",
        {
            **emitted,
            "rounds": rounds,
            "conflicting_lexical_hashes": len(conflict_hashes),
            "parse_rejected_ids": sorted(excluded - initial_excluded),
            "explicitly_excluded_ids": sorted(initial_excluded),
        },
    )
    db.close()
    input_hashes = []
    for path in sorted(inputs):
        value = (
            inventory.get("cvefixes_cache_sha256")
            if path.name == "CVEfixes.db"
            else digest(path)
        )
        input_hashes.append(
            {"path": str(path), "bytes": path.stat().st_size, "sha256": value}
        )
    dump(output / "input-manifest.json", input_hashes)
    dump(
        output / "manifest.json",
        {
            "schema_version": "aegislm.cc-source-corpus-build.v1",
            "seed": seed,
            "split_sizes": SIZES,
            "source_counts": {
                split: dict(
                    Counter(
                        row["provenance"]["dataset"]
                        for row in final_rows
                        if row["split"] == split
                    )
                )
                for split in SIZES
            },
            "label_counts": {
                split: dict(
                    Counter(
                        row["assessment"] for row in final_rows if row["split"] == split
                    )
                )
                for split in SIZES
            },
            "approved_for_training": False,
            "decision_status": "source_label_and_cwe_review_required",
            "evidence_training_records": 0,
            "evidence_status": "no_verified_line_annotations",
            "split_audit_pass": emitted["pass"],
            "normalization_counts": dict(stats),
            "split_policy": "project-function-family/CVE/commit/lexical/identifier-normalized components before seed sampling; cross-split 5-gram Jaccard >=0.8 components merged until zero; trivial functions <25 tokens cannot bridge projects by clone hashes",
            "normalized_pool_path": str(pool),
            "historical_policy": "exclude components touching prior phase-f-source train/validation/challenge lexical or identifier-normalized fingerprints",
            "limitations": [
                "source labels and single-CWE metadata are provisional, not human verified",
                "no fabricated evidence, confidence, or uncertain targets",
                "not an official original dataset benchmark split",
                "near-clone checks do not prove arbitrary semantic independence",
                "tokenizer length audit is required before training",
                "CVEfixes uses hash-verified prior raw SQL import; function labels are not inferred from commit membership",
            ],
            "command": sys.argv,
            "python_version": sys.version,
            "package_versions": {
                name: importlib.metadata.version(name)
                for name in [
                    "pyarrow",
                    "tree-sitter",
                    "tree-sitter-c",
                    "tree-sitter-cpp",
                    "duckdb",
                ]
            },
            "builder_sha256": digest(Path(__file__)),
            "normalizer_sha256": digest(
                Path(__file__).resolve().parents[1]
                / "aegislm/datasets/source_corpus.py"
            ),
        },
    )
    with (output / "SHA256SUMS").open("x") as stream:
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "SHA256SUMS":
                stream.write(f"{digest(path)}  {path.relative_to(output)}\n")
    print(
        json.dumps(json.loads((output / "manifest.json").read_text()), indent=2),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw_data"))
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/cc-source-candidates-20260928-v1"),
    )
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--reuse-pool", type=Path)
    parser.add_argument("--exclude-ids", type=Path)
    args = parser.parse_args()
    build(
        args.raw,
        args.processed,
        args.output,
        args.seed,
        args.reuse_pool,
        args.exclude_ids,
    )


if __name__ == "__main__":
    main()
