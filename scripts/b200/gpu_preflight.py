"""Check the selected B200 device and record its actual runtime before training."""

import json
import subprocess
from pathlib import Path

import torch

root = Path(__file__).resolve().parents[2]
assert torch.cuda.is_available()
assert torch.version.cuda == "13.0", "Expected the original CUDA 13.0 PyTorch build"
assert torch.cuda.device_count() == 1, "Select one GPU using CUDA_VISIBLE_DEVICES"
properties = torch.cuda.get_device_properties(0)
assert "B200" in properties.name, properties.name
assert torch.cuda.is_bf16_supported()
a = torch.ones((64, 64), device="cuda", dtype=torch.bfloat16)
assert float((a @ a)[0, 0]) == 64.0
torch.cuda.synchronize()
report = {
    "status": "passed",
    "torch": torch.__version__,
    "cuda": torch.version.cuda,
    "gpu": properties.name,
    "vram_bytes": properties.total_memory,
    "capability": torch.cuda.get_device_capability(0),
    "compiled_arches": torch.cuda.get_arch_list(),
    "nvidia_smi": subprocess.check_output(["nvidia-smi"], text=True),
}
path = root / "outputs/b200-gpu-preflight.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
