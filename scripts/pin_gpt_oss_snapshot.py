"""Verify official pinned HF snapshot bytes and write a local attestation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from huggingface_hub import HfApi

REPO = "openai/gpt-oss-20b"
REVISION = "6cee5e81ee83917806bbde320786a8fb61efebee"
ROOT = Path("<WORKSPACE>/LLM/Model/base/gpt-oss-20b-6cee5e81")


def main() -> None:
    info = HfApi().model_info(REPO, revision=REVISION, files_metadata=True)
    assert info.sha == REVISION
    files = {}
    for item in info.siblings:
        name = item.rfilename
        if "/" in name or not (name.endswith((".json", ".jinja", ".safetensors")) or name in ("LICENSE", "USAGE_POLICY")):
            continue
        path = ROOT / name
        size = path.stat().st_size
        sha256 = hashlib.sha256()
        git_blob = hashlib.sha1(f"blob {size}\0".encode())
        with path.open("rb") as f:
            for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
                sha256.update(block)
                git_blob.update(block)
        if item.lfs:
            if sha256.hexdigest() != item.lfs.sha256:
                raise ValueError(f"official LFS SHA mismatch: {name}")
        elif git_blob.hexdigest() != item.blob_id:
            raise ValueError(f"official Git blob mismatch: {name}")
        files[name] = {"sha256": sha256.hexdigest(), "size": size}
        print("verified", name, flush=True)
    if len(files) != 12:
        raise ValueError("unexpected pinned snapshot file set")
    result = ROOT / "pilot_snapshot_attestation.json"
    result.write_text(json.dumps({"repo_id": REPO, "revision": REVISION, "verified_against": "HF pinned commit blob/LFS hashes", "files": files}, indent=2) + "\n")
    print("ATTESTATION_SHA256", hashlib.sha256(result.read_bytes()).hexdigest(), flush=True)


if __name__ == "__main__":
    main()
