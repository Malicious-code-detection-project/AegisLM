"""Source-corpus normalization and leakage checks, independent of model runtimes."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

# Quoted strings are matched before comments, so URLs and comment-like literals survive.
LEXEME = re.compile(
    r'R"(?P<delimiter>[^ ()\\\t\r\n]{0,16})\(.*?\)(?P=delimiter)"'
    r'|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    r"|/\*.*?\*/|//[^\n]*|[A-Za-z_][A-Za-z_0-9]*"
    r"|(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d+)?)[a-zA-Z]*"
    r"|>>=|<<=|->\*|\.\*|::|->|\+\+|--|&&|\|\||==|!=|<=|>="
    r"|\+=|-=|\*=|/=|%=|<<|>>|[^\s]",
    re.DOTALL,
)
KEYWORDS = frozenset(
    "alignas alignof asm auto bool break case catch char class const constexpr "
    "continue decltype default delete do double else enum explicit extern false "
    "float for friend goto if inline int long namespace new noexcept nullptr "
    "operator private protected public register reinterpret_cast return short "
    "signed sizeof static static_cast struct switch template this throw true try "
    "typedef typename union unsigned using virtual void volatile wchar_t while "
    "_Bool _Atomic _Thread_local".split()
)


def sha(text: str) -> str:
    """Return a stable UTF-8 SHA-256 digest."""
    return hashlib.sha256(text.encode()).hexdigest()


def tokens(code: str, *, abstract: bool = False) -> list[str]:
    """Tokenize without comments; optionally normalize identifier names only."""
    result = []
    for match in LEXEME.finditer(code):
        token = match.group()
        if token.startswith(("//", "/*")):
            continue
        if abstract and re.fullmatch(r"[A-Za-z_]\w*", token) and token not in KEYWORDS:
            token = "IDENT"
        result.append(token)
    return result


def clean_code(code: str, *, juliet: bool = False) -> str:
    """Remove annotation comments while preserving lines and literal contents."""

    def replace(match: re.Match[str]) -> str:
        token = match.group()
        if token.startswith(("//", "/*")):
            return " " + "\n" * token.count("\n")
        if juliet and re.fullmatch(r"[A-Za-z_]\w*", token):
            if re.search(r"good|bad|CWE\d+", token, flags=re.IGNORECASE):
                # Per-function stable neutral identifiers remove synthetic label cues.
                if token not in names:
                    names[token] = f"symbol_{len(names)}"
                return names[token]
        return token

    names: dict[str, str] = {}
    return LEXEME.sub(replace, code.replace("\r\n", "\n").replace("\r", "\n")).strip()


def fingerprints(code: str) -> tuple[str, str, str]:
    """Hash exact code, lexical tokens, and identifier-normalized tokens."""
    return (
        sha(code),
        sha("\0".join(tokens(code))),
        sha("\0".join(tokens(code, abstract=True))),
    )


def normalize_project(project: str) -> str:
    """Conservatively merge matching repository basenames across data providers."""
    value = project.lower().strip().rstrip("/").removesuffix(".git")
    return re.sub(r"[^a-z0-9]", "", value.split("/")[-1])


def function_family(code: str) -> str | None:
    """Conservative declaration-name key; complex declarations may be unknown."""
    header = code.split("{", 1)[0]
    names = re.findall(r"([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)\s*\(", header)
    excluded = {"__attribute__", "__declspec", "sizeof", "decltype", "noexcept"}
    return next((name for name in names if name not in excluded), None)


class Components:
    """Deterministic transitive groups for provenance and clone connections."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, key: str) -> str:
        self.parent.setdefault(key, key)
        root = key
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[key] != key:
            previous = self.parent[key]
            self.parent[key] = root
            key = previous
        return root

    def union(self, keys: Iterable[str]) -> str:
        roots = sorted({self.find(key) for key in keys})
        if not roots:
            raise ValueError("empty component")
        for root in roots[1:]:
            self.parent[root] = roots[0]
        return roots[0]


def split_for_group(group: str, seed: int) -> str:
    """Assign a group before sampling; never change assignment to improve metrics."""
    bucket = int(sha(f"{seed}:{group}")[:16], 16) % 100
    return "train" if bucket < 80 else "validation" if bucket < 90 else "test"


def near_clone_pairs(
    records: Sequence[dict[str, Any]], *, threshold: float = 0.8
) -> list[tuple[int, int]]:
    """Exact prefix-filtered Jaccard join on identifier-normalized token 5-grams.

    Only cross-split pairs are returned. This detects the stated lexical clone
    class, not arbitrary semantic equivalence. No probabilistic LSH is used.
    """
    if not 0 < threshold <= 1:
        raise ValueError("threshold must be in (0, 1]")
    sets: list[set[tuple[str, ...]]] = []
    for row in records:
        ts = tokens(row["source_code"], abstract=True)
        sets.append({tuple(ts[i : i + 5]) for i in range(max(1, len(ts) - 4))})
    frequency: Counter[tuple[str, ...]] = Counter()
    for values in sets:
        frequency.update(values)
    postings: dict[tuple[str, ...], list[int]] = defaultdict(list)
    pairs = []
    for index in sorted(range(len(sets)), key=lambda i: (len(sets[i]), i)):
        values = sets[index]
        ordered = sorted(values, key=lambda item: (frequency[item], item))
        prefix = ordered[: len(values) - math.ceil(threshold * len(values)) + 1]
        candidates: set[int] = set()
        for token in prefix:
            candidates.update(postings[token])
        for previous in sorted(candidates):
            other = sets[previous]
            if records[index]["split"] == records[previous]["split"]:
                continue
            if len(other) < threshold * len(values):
                continue
            common = len(values & other)
            if common >= threshold * (len(values) + len(other) - common):
                pairs.append((previous, index))
        for token in prefix:
            postings[token].append(index)
    return pairs


DECISION_PROMPT = """You are AegisLM, a defensive source-code vulnerability decision model.
Using only the requested CWE and supplied function, return exactly one JSON
object with assessment: present, not_observed, or uncertain. Scope the decision
to the supplied function and requested CWE. Use uncertain when the function
does not supply enough information. Do not add Markdown or other fields."""


def decision_messages(record: dict[str, Any], *, answer: bool) -> list[dict[str, str]]:
    """Export only task-visible fields; source labels remain explicitly provisional."""
    if record["assessment"] not in {"present", "not_observed"}:
        raise ValueError("missing binary source label")
    if not re.fullmatch(r"CWE-[1-9]\d*", record["target_cwe"] or ""):
        raise ValueError("missing unambiguous CWE")
    messages = [
        {"role": "system", "content": DECISION_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "scope": {
                        "target_cwe": record["target_cwe"],
                        "boundary": "supplied_function",
                    },
                    "source_code": record["source_code"],
                },
                ensure_ascii=False,
            ),
        },
    ]
    if answer:
        messages.append(
            {
                "role": "assistant",
                "content": json.dumps({"assessment": record["assessment"]}),
            }
        )
    return messages


def audit_splits(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Recompute fingerprints from final records and reject split leakage."""
    seen: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in records:
        exact, lexical, abstract = fingerprints(row["source_code"])
        for field, key in [
            ("id", row["id"]),
            ("group_id", row["group_id"]),
            ("exact", exact),
            ("lexical", lexical),
            ("abstract", abstract),
        ]:
            seen[field][key].add(row["split"])
        provenance = row.get("provenance", {})
        if provenance.get("commit"):
            seen["commit"][provenance["commit"]].add(row["split"])
        for cve in re.findall(r"CVE-\d{4}-\d+", json.dumps(provenance.get("cves"))):
            seen["cve"][cve].add(row["split"])
        project = normalize_project(provenance.get("project") or "")
        family = function_family(row["source_code"])
        if provenance.get("dataset") == "juliet":
            seen["juliet_family"][project].add(row["split"])
        elif project and family:
            seen["project_function"][f"{project}:{family}"].add(row["split"])
    overlap = {
        field: sum(len(splits) > 1 for splits in values.values())
        for field, values in seen.items()
    }
    duplicates = len(records) - len({row["id"] for row in records})
    return {
        "cross_split_overlap": overlap,
        "duplicate_ids": duplicates,
        "pass": not any(overlap.values()) and duplicates == 0,
    }


def normalize_record(row: dict[str, Any]) -> dict[str, Any] | None:
    """Retain source annotations without promoting them to verified gold."""
    code = row["code"]
    if not isinstance(code, str) or not code.strip():
        return None
    code = clean_code(code, juliet=row["dataset"] == "juliet")
    cwes = sorted(set(re.findall(r"CWE-[1-9]\d*", json.dumps(row["cwes"]))))
    label = row["label"]
    exact, lexical, abstract = fingerprints(code)
    return {
        "schema_version": "aegislm.cc-source-candidate.v1",
        "id": "cc-" + sha(f"{row['dataset']}:{row['original_id']}")[:24],
        "group_id": None,
        "split": None,
        "language": row["language"],
        "source_code": code,
        "target_cwe": cwes[0] if len(cwes) == 1 else None,
        "assessment": "present"
        if label == 1
        else "not_observed"
        if label == 0
        else None,
        "evidence_ranges": None,
        "hashes": {"exact": exact, "lexical": lexical, "abstract": abstract},
        "provenance": {
            key: row.get(key)
            for key in [
                "dataset",
                "original_id",
                "project",
                "commit",
                "cves",
                "file",
                "input_file",
                "input_row",
                "before_change",
            ]
        },
        "annotation": {
            "decision_status": "source_label_unreviewed"
            if label is not None
            else "unlabeled",
            "cwe_status": "source_metadata_unreviewed" if cwes else "missing",
            "cwe_candidates": cwes,
            "evidence_status": "unreviewed",
            "method": "source_annotation_only",
            "license_status": "review_required",
            "approved_for_training": False,
        },
    }
