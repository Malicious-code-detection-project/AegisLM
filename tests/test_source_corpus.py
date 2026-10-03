"""Regression tests for corpus leakage and source-label boundaries."""

import random

import pytest

from aegislm.datasets.source_corpus import (
    Components,
    audit_splits,
    clean_code,
    decision_messages,
    fingerprints,
    function_family,
    near_clone_pairs,
    normalize_record,
    split_for_group,
    tokens,
)


def test_comments_are_removed_without_corrupting_literals() -> None:
    source = 'char *url="https://host/a/*b*/"; /* BAD\ncomment */\nreturn 0; // FLAW'
    cleaned = clean_code(source)
    assert '"https://host/a/*b*/"' in cleaned
    assert "BAD" not in cleaned and "FLAW" not in cleaned
    assert cleaned.count("\n") == source.count("\n")
    raw = 'auto x = R"tag(a // b /* c */)tag"; /* remove */'
    assert 'R"tag(a // b /* c */)tag"' in clean_code(raw)


def test_juliet_identifiers_do_not_expose_labels() -> None:
    good = clean_code(
        "void CWE123_good(){ int goodValue=1; use(goodValue); }", juliet=True
    )
    bad = clean_code("void CWE123_bad(){ int badValue=1; use(badValue); }", juliet=True)
    assert good == bad
    assert "CWE123" not in good


def test_fingerprints_ignore_comments_and_names_but_keep_constants() -> None:
    first = fingerprints("int foo(int x){return x+1;}")
    second = fingerprints("int bar(int y) { /* note */ return y + 1; }")
    different = fingerprints("int bar(int y){return y+2;}")
    assert first[1] != second[1]
    assert first[2] == second[2]
    assert first[2] != different[2]


def test_groups_are_transitive_and_order_independent() -> None:
    first, second = Components(), Components()
    for keys in [("a", "b"), ("c", "d"), ("b", "d")]:
        first.union(keys)
    for keys in [("b", "d"), ("c", "d"), ("a", "b")]:
        second.union(keys)
    assert {first.find(key) for key in "abcd"} == {"a"}
    assert {second.find(key) for key in "abcd"} == {"a"}
    assert split_for_group(first.find("d"), 3407) == split_for_group(
        second.find("c"), 3407
    )


def test_function_family_keeps_revisions_together_without_grouping_whole_repo() -> None:
    assert function_family("int parse(char *p) {return 1;}") == "parse"
    assert function_family("int parse(char *p, int size) {return size;}") == "parse"
    assert (
        function_family("void ns::Socket::close() const {cleanup();}")
        == "ns::Socket::close"
    )
    assert function_family("int unrelated(){return 1;}") != "parse"


def test_canonical_preserves_missing_and_ambiguous_annotations() -> None:
    raw = dict(
        dataset="cvefixes",
        original_id="method-1",
        code="int f(){return 1;}",
        language="C",
        label=None,
        cwes=["CWE-125", "CWE-787"],
        project="example",
        commit="a",
        cves="CVE-2020-1234",
    )
    record = normalize_record(raw)
    assert record is not None
    assert record["assessment"] is None and record["target_cwe"] is None
    assert record["evidence_ranges"] is None
    assert record["annotation"]["cwe_candidates"] == ["CWE-125", "CWE-787"]
    assert not record["annotation"]["approved_for_training"]


def test_final_audit_recomputes_hashes_instead_of_trusting_metadata() -> None:
    rows = [
        {
            "id": "a",
            "group_id": "g1",
            "split": "train",
            "source_code": "int f(){return 1;}",
        },
        {
            "id": "b",
            "group_id": "g2",
            "split": "test",
            "source_code": "int g(){return 1;}",
        },
    ]
    audit = audit_splits(rows)
    assert not audit["pass"]
    assert audit["cross_split_overlap"]["abstract"] == 1


def test_near_clone_prefix_join_matches_exhaustive_comparison() -> None:
    rng = random.Random(34)
    rows = []
    for i in range(55):
        numbers = list(range(30))
        for _ in range(rng.randrange(0, 5)):
            numbers[rng.randrange(30)] = rng.randrange(50)
        code = "int f(){" + "".join(f"x += {n};" for n in numbers) + "return x;}"
        rows.append({"source_code": code, "split": "train" if i % 2 else "test"})
    grams = []
    for row in rows:
        ts = tokens(row["source_code"], abstract=True)
        grams.append({tuple(ts[i : i + 5]) for i in range(len(ts) - 4)})
    expected = set()
    for i in range(len(rows)):
        for j in range(i):
            if (
                rows[i]["split"] != rows[j]["split"]
                and len(grams[i] & grams[j]) / len(grams[i] | grams[j]) >= 0.8
            ):
                expected.add((j, i))
    actual = {tuple(sorted(pair)) for pair in near_clone_pairs(rows)}
    assert actual == expected
    assert actual


def test_audit_checks_cve_and_commit_even_if_group_ids_are_forged() -> None:
    rows = [
        {
            "id": "a",
            "group_id": "fake-a",
            "split": "train",
            "source_code": "int f(){return 1;}",
            "provenance": {"commit": "same-fix", "cves": ["CVE-2020-1234"]},
        },
        {
            "id": "b",
            "group_id": "fake-b",
            "split": "test",
            "source_code": "void g(){log(3);}",
            "provenance": {"commit": "same-fix", "cves": ["CVE-2020-1234"]},
        },
    ]
    audit = audit_splits(rows)
    assert not audit["pass"]
    assert audit["cross_split_overlap"]["commit"] == 1
    assert audit["cross_split_overlap"]["cve"] == 1


def test_unlabeled_is_not_silently_converted_to_negative() -> None:
    with pytest.raises(ValueError, match="binary source label"):
        decision_messages({"assessment": None, "target_cwe": "CWE-125"}, answer=True)
    with pytest.raises(ValueError, match="unambiguous CWE"):
        decision_messages({"assessment": "present", "target_cwe": None}, answer=True)


def test_challenge_contains_neither_gold_nor_provenance() -> None:
    record = {
        "assessment": "present",
        "target_cwe": "CWE-125",
        "source_code": "int f(){return 1;}",
        "provenance": {"project": "private-project", "commit": "gold-commit"},
    }
    challenge = decision_messages(record, answer=False)
    assert [message["role"] for message in challenge] == ["system", "user"]
    assert "private-project" not in str(challenge)
    assert "gold-commit" not in str(challenge)
    assert (
        decision_messages(record, answer=True)[-1]["content"]
        == '{"assessment": "present"}'
    )
