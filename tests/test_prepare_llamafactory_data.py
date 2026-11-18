from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_prepare_llamafactory_data_registers_train_and_validation(tmp_path: Path):
    llamafactory_data = tmp_path / "LLaMA-Factory" / "data"
    llamafactory_data.mkdir(parents=True)
    dataset_info = llamafactory_data / "dataset_info.json"
    dataset_info.write_text('{"identity": {"file_name": "identity.json"}}\n')

    script = Path("scripts/prepare_llamafactory_data.py")
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--llamafactory-dir",
            str(tmp_path / "LLaMA-Factory"),
        ],
        check=True,
    )

    parsed = json.loads(dataset_info.read_text(encoding="utf-8"))

    assert "identity" in parsed
    assert parsed["aegislm_security_sft_train"]["file_name"] == (
        "aegislm_security_sft_train.json"
    )
    assert parsed["aegislm_security_sft_validation"]["columns"]["system"] == "system"
