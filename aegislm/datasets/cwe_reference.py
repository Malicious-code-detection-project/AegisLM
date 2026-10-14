"""Versioned English CWE references; no training or model execution."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET

from aegislm.artifacts import validate_artifact_output_location

SCHEMA = "aegislm.cwe-reference.v1"
NAMESPACE = "http://cwe.mitre.org/cwe-7"
# Examples and CVE references are preserved in the archive, not retrieved.
REFERENCE_SECTIONS = (
    "Description",
    "Extended_Description",
    "Alternate_Terms",
    "Related_Weaknesses",
    "Applicable_Platforms",
    "Common_Consequences",
    "Detection_Methods",
    "Potential_Mitigations",
    "Mapping_Notes",
)
CONTAINERS = {"Weaknesses": "Weakness", "Categories": "Category", "Views": "View"}


def local_name(tag: str) -> str:
    """Return an XML name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def xml_tree(node: ET.Element) -> dict[str, Any]:
    """Preserve element order, attributes, mixed text and namespaces in JSON."""
    return {
        "tag": node.tag,
        "attributes": dict(node.attrib),
        "text": node.text,
        "tail": node.tail,
        "children": [xml_tree(child) for child in node],
    }


def normalized_text(node: ET.Element) -> str:
    """Separate HTML blocks while preserving adjacent inline text."""
    parts = [node.text or ""]
    for child in node:
        block = local_name(child.tag) in {"p", "div", "li", "br", "ul", "ol", "pre"}
        parts.extend(
            [
                " " if block else "",
                normalized_text(child),
                " " if block else "",
                child.tail or "",
            ]
        )
    # Only collapse whitespace at the caller boundary: recursive stripping would
    # lose spaces around inline markup (e.g. 'a <b>buffer</b> read').
    return "".join(parts)


def section_text(node: ET.Element) -> str:
    """Keep attribute-only relationships and nested field labels readable."""
    if not len(node):
        attrs = "; ".join(f"{local_name(k)}={v}" for k, v in node.attrib.items())
        return ": ".join(
            part for part in (attrs, " ".join(normalized_text(node).split())) if part
        )
    if any(child.tag.startswith("{http://www.w3.org/1999/xhtml}") for child in node):
        return " ".join(normalized_text(node).split())
    lines = [node.text.strip()] if node.text and node.text.strip() else []
    for child in node:
        lines.append(f"{local_name(child.tag)}: {section_text(child)}")
        if child.tail and child.tail.strip():
            lines.append(child.tail.strip())
    if node.attrib:
        lines.insert(
            0, "; ".join(f"{local_name(k)}={v}" for k, v in node.attrib.items())
        )
    return "\n".join(lines)


def parse_catalog(payload: bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Parse CWE XML, rejecting invalid identities before creating artifacts."""
    # Official CWE is UTF-8 without DTDs; avoid entity expansion or external DTDs.
    text = payload.decode("utf-8-sig")
    if re.search(r"<!\s*(DOCTYPE|ENTITY)\b", text, re.IGNORECASE):
        raise ValueError("DTD and entity declarations are not supported")
    root = ET.fromstring(text)
    if root.tag != f"{{{NAMESPACE}}}Weakness_Catalog":
        raise ValueError("Expected a CWE 7 Weakness_Catalog")
    if not root.get("Version") or not root.get("Date"):
        raise ValueError("Catalog version and date are required")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for container in root:
        kind = CONTAINERS.get(local_name(container.tag))
        if kind is None:
            continue
        for node in container:
            ident = node.get("ID", "")
            if node.tag != f"{{{NAMESPACE}}}{kind}" or not re.fullmatch(
                r"[1-9]\d*", ident
            ):
                raise ValueError("Invalid CWE entry type or ID")
            if ident in seen:
                raise ValueError(f"Duplicate CWE ID: {ident}")
            seen.add(ident)
            if not node.get("Name") or not node.get("Status"):
                raise ValueError(f"Missing name or status: CWE-{ident}")
            sections = {
                local_name(child.tag): section_text(child)
                for child in node
                if local_name(child.tag) in REFERENCE_SECTIONS
            }
            records.append(
                {
                    "id": f"CWE-{ident}",
                    "kind": kind,
                    "name": node.attrib["Name"],
                    "status": node.attrib["Status"],
                    "abstraction": node.get("Abstraction"),
                    "catalog_version": root.attrib["Version"],
                    "source_url": f"https://cwe.mitre.org/data/definitions/{ident}.html",
                    "sections": sections,
                }
            )
    if not any(record["kind"] == "Weakness" for record in records):
        raise ValueError("Catalog must contain weaknesses")
    records.sort(key=lambda record: int(record["id"][4:]))
    return xml_tree(root), records


def markdown(record: dict[str, Any]) -> str:
    """Render a reference projection, without asserting an official translation."""
    lines = [
        f"# {record['id']}: {record['name']}",
        "",
        f"Type: {record['kind']} | Status: {record['status']} | "
        f"Abstraction: {record['abstraction'] or 'N/A'}",
        f"CWE version: {record['catalog_version']}",
        f"Source: {record['source_url']}",
        "",
        "Derived English reference, not a vulnerability verdict. "
        "Examples, observed cases, references and history are omitted here; "
        "the full XML structure is retained in catalog.json.",
    ]
    for name, value in record["sections"].items():
        lines.extend(["", f"## {name.replace('_', ' ')}", "", value])
    lines.extend(
        [
            "",
            "CWE content: Copyright © The MITRE Corporation. "
            "CWE is a trademark of The MITRE Corporation. "
            "See [the preserved license and terms](../TERMS.html).",
        ]
    )
    return "\n".join(lines) + "\n"


def build_reference(
    xml_path: Path, terms_path: Path, output: Path, source_url: str
) -> dict[str, Any]:
    """Create an immutable local reference bundle; manifest is written last."""
    validate_artifact_output_location(output)
    payload, terms = xml_path.read_bytes(), terms_path.read_bytes()
    if not terms.strip():
        raise ValueError("Preserved license/terms must not be empty")
    archive, records = parse_catalog(payload)
    output.mkdir(parents=True, exist_ok=False)
    (output / "markdown").mkdir()
    (output / "source.xml").write_bytes(payload)
    (output / "TERMS.html").write_bytes(terms)
    (output / "catalog.json").write_text(
        json.dumps(archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "entries.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    for record in records:
        if record["kind"] == "Weakness":
            (output / "markdown" / f"{record['id']}.md").write_text(
                markdown(record), encoding="utf-8"
            )
    files = sorted(path for path in output.rglob("*") if path.is_file())
    manifest = {
        "schema": SCHEMA,
        "catalog_version": archive["attributes"]["Version"],
        "catalog_date": archive["attributes"]["Date"],
        "source_url": source_url,
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "language": "en",
        "entry_counts": dict(Counter(record["kind"] for record in records)),
        "reference_sections": list(REFERENCE_SECTIONS),
        "module_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "files": {
            path.relative_to(output).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in files
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def load_reference(output: Path) -> list[dict[str, Any]]:
    """Require a completed bundle and verify the retrieved projection digest."""
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise ValueError("Unsupported reference schema")
    payload = (output / "entries.jsonl").read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest["files"]["entries.jsonl"]:
        raise ValueError("Reference entries changed since build")
    return [json.loads(line) for line in payload.decode("utf-8").splitlines()]


def lookup(records: list[dict[str, Any]], ident: str) -> dict[str, Any]:
    """Look up any entry by explicit CWE ID, including deprecated entries."""
    match = re.fullmatch(r"(?:CWE-)?([1-9]\d*)", ident.strip(), re.IGNORECASE)
    if match is None:
        raise ValueError("Expected CWE-<positive integer>")
    target = f"CWE-{match[1]}"
    for record in records:
        if record["id"] == target:
            return record
    raise KeyError(target)


def search(
    records: list[dict[str, Any]], query: str, limit: int = 5
) -> list[dict[str, Any]]:
    """Rank English term matches; this score is not a model confidence."""
    if not 1 <= limit <= 50:
        raise ValueError("Search limit must be between 1 and 50")
    query = query.strip()
    if not query:
        raise ValueError("Search query must not be empty")
    if re.fullmatch(r"(?:CWE-)?[1-9]\d*", query, re.IGNORECASE):
        try:
            record = lookup(records, query)
        except KeyError:
            return []
        return (
            [record]
            if record["kind"] == "Weakness" and record["status"] != "Deprecated"
            else []
        )
    terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for record in records:
        if record["kind"] != "Weakness" or record["status"] == "Deprecated":
            continue
        title = set(re.findall(r"[a-z0-9]+", record["name"].lower()))
        body = set(
            re.findall(r"[a-z0-9]+", " ".join(record["sections"].values()).lower())
        )
        score = 5 * len(terms & title) + len(terms & body)
        if score:
            ranked.append((score, int(record["id"][4:]), record))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [dict(record, search_score=score) for score, _, record in ranked[:limit]]
