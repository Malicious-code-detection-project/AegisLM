"""Reference fidelity, retrieval boundaries and non-clobbering behavior."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import pytest

from aegislm.datasets.cwe_reference import (
    build_reference,
    load_reference,
    lookup,
    markdown,
    parse_catalog,
    search,
)


@pytest.fixture
def catalog() -> bytes:
    # Synthetic catalog; no downloaded dataset or vulnerability code in tests.
    return b"""<Weakness_Catalog xmlns="http://cwe.mitre.org/cwe-7"
        xmlns:h="http://www.w3.org/1999/xhtml" Version="test-1" Date="2026-10-12">
      <Weaknesses>
        <Weakness ID="125" Name="Out-of-bounds Read" Status="Stable" Abstraction="Base">
          <Description>A buffer read.</Description>
          <Extended_Description><h:p>A <h:b>buffer</h:b> read.</h:p><h:p>Another paragraph.</h:p></Extended_Description>
          <Related_Weaknesses><Related_Weakness Nature="ChildOf" CWE_ID="119" View_ID="1000"/></Related_Weaknesses>
          <Observed_Examples><Observed_Example><Reference>CVE-secretcase</Reference></Observed_Example></Observed_Examples>
          <Demonstrative_Examples><Demonstrative_Example><Body_Text>secretcode</Body_Text></Demonstrative_Example></Demonstrative_Examples>
          <References><Reference External_Reference_ID="secretreference"/></References>
          <Content_History><Submission><Submission_Name>secrethistory</Submission_Name></Submission></Content_History>
        </Weakness>
        <Weakness ID="416" Name="Use After Free" Status="Incomplete" Abstraction="Variant">
          <Description>Access after release; a buffer read may occur.</Description>
          <Mapping_Notes><Usage>ALLOWED</Usage><Rationale>Inspect the cause.</Rationale></Mapping_Notes>
        </Weakness>
        <Weakness ID="999" Name="DEPRECATED: Buffer Read" Status="Deprecated" Abstraction="Base">
          <Description>A retired entry.</Description>
        </Weakness>
      </Weaknesses>
      <Categories><Category ID="100" Name="Buffer Read Category" Status="Stable"/></Categories>
      <Views><View ID="1000" Name="Buffer Read View" Status="Stable" Type="Graph"/></Views>
      <External_References><External_Reference Reference_ID="secretreference"><Title>archiveonlytitle</Title></External_Reference></External_References>
    </Weakness_Catalog>"""


def test_archive_preserves_element_tree_and_projection_excludes_examples(
    catalog: bytes,
) -> None:
    archive, records = parse_catalog(catalog)

    def restore(tree: dict[str, Any]) -> ET.Element:
        element = ET.Element(tree["tag"], tree["attributes"])
        element.text, element.tail = tree["text"], tree["tail"]
        element.extend(restore(child) for child in tree["children"])
        return element

    assert ET.tostring(restore(archive)) == ET.tostring(ET.fromstring(catalog))
    entry = lookup(records, "cwe-125")
    assert (
        entry["sections"]["Extended_Description"] == "A buffer read. Another paragraph."
    )
    assert "CWE_ID=119" in entry["sections"]["Related_Weaknesses"]
    assert "ALLOWED" in lookup(records, "416")["sections"]["Mapping_Notes"]
    for excluded in (
        "secretcase",
        "secretcode",
        "secretreference",
        "secrethistory",
        "archiveonlytitle",
    ):
        assert excluded in json.dumps(archive)
        assert excluded not in json.dumps(records)
        assert excluded not in markdown(entry)
        assert search(records, excluded) == []


def test_lookup_and_ranked_search(catalog: bytes) -> None:
    _, records = parse_catalog(catalog)
    assert [entry["id"] for entry in search(records, "buffer read")] == [
        "CWE-125",
        "CWE-416",
    ]
    assert search(records, "use after free")[0]["id"] == "CWE-416"
    assert search(records, "CWE-125")[0]["id"] == "CWE-125"
    assert lookup(records, "999")["status"] == "Deprecated"
    assert lookup(records, "100")["kind"] == "Category"
    assert lookup(records, "1000")["kind"] == "View"
    assert search(records, "CWE-999") == []
    assert search(records, "CWE-100") == []
    assert search(records, "CWE-1000") == []
    assert search(records, "CWE-404") == []
    with pytest.raises(KeyError):
        lookup(records, "404")
    with pytest.raises(ValueError):
        lookup(records, "../125")
    with pytest.raises(ValueError):
        search(records, " ")
    with pytest.raises(ValueError):
        search(records, "read", limit=0)
    with pytest.raises(ValueError):
        search(records, "read", limit=51)


def test_search_ties_use_numeric_id(catalog: bytes) -> None:
    _, records = parse_catalog(catalog)
    assert [entry["id"] for entry in search(list(reversed(records)), "buffer")] == [
        "CWE-125",
        "CWE-416",
    ]


@pytest.mark.parametrize(
    ("old", "new", "error"),
    [
        (b'ID="416"', b'ID="125"', "Duplicate"),
        (b'ID="125"', b'ID="../125"', "Invalid"),
        (b'Version="test-1"', b"", "version and date"),
        (b'Status="Stable"', b"", "Missing name or status"),
        (b"cwe-7", b"cwe-8", "Expected"),
    ],
)
def test_invalid_catalog_rejected(
    catalog: bytes, old: bytes, new: bytes, error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        parse_catalog(catalog.replace(old, new))


def test_dtd_rejected(catalog: bytes) -> None:
    with pytest.raises(ValueError, match="DTD"):
        parse_catalog(
            b'<!DOCTYPE Weakness_Catalog [<!ENTITY x "expansion">]>' + catalog
        )


def test_build_integrity_and_no_overwrite(tmp_path: Path, catalog: bytes) -> None:
    source, terms = tmp_path / "input.xml", tmp_path / "terms.html"
    source.write_bytes(catalog)
    terms.write_text("Synthetic license fixture", encoding="utf-8")
    output = tmp_path / "reference"
    manifest = build_reference(source, terms, output, "https://example.org/catalog.xml")
    assert manifest["entry_counts"] == {"Weakness": 3, "Category": 1, "View": 1}
    assert manifest["source_sha256"] == hashlib.sha256(catalog).hexdigest()
    assert (output / "source.xml").read_bytes() == catalog
    assert (output / "TERMS.html").read_bytes() == terms.read_bytes()
    assert len(list((output / "markdown").glob("*.md"))) == 3
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    assert len(load_reference(output)) == 5
    with pytest.raises(FileExistsError):
        build_reference(source, terms, output, "https://example.org/catalog.xml")
    assert json.loads((output / "manifest.json").read_text()) == manifest
    (output / "entries.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        load_reference(output)


def test_reject_before_output_creation(tmp_path: Path, catalog: bytes) -> None:
    source, terms = tmp_path / "input.xml", tmp_path / "terms.html"
    source.write_bytes(catalog.replace(b'ID="416"', b'ID="125"'))
    terms.write_text("License", encoding="utf-8")
    output = tmp_path / "reference"
    with pytest.raises(ValueError, match="Duplicate"):
        build_reference(source, terms, output, "https://example.org/catalog.xml")
    assert not output.exists()
    source.write_bytes(catalog)
    terms.write_text(" ", encoding="utf-8")
    with pytest.raises(ValueError, match="terms"):
        build_reference(source, terms, output, "https://example.org/catalog.xml")
    assert not output.exists()


def test_symlink_output_rejected(tmp_path: Path, catalog: bytes) -> None:
    source, terms = tmp_path / "input.xml", tmp_path / "terms.html"
    source.write_bytes(catalog)
    terms.write_text("License", encoding="utf-8")
    destination = tmp_path / "real"
    destination.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        build_reference(
            source, terms, alias / "reference", "https://example.org/catalog.xml"
        )
    assert not (destination / "reference").exists()
