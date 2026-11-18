#!/usr/bin/env bash
set -euo pipefail
cd <HOME>/workspace/AegisLM
PY=<HOME>/workspace/AegisLM_Mistral-small-4-119B/.venv/bin/python
CONFIG=<HOME>/workspace/AegisLM/configs/gpt_oss_qwen_100_20260921.json
export HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TOKENIZERS_PARALLELISM=false WANDB_MODE=disabled PYTHONUNBUFFERED=1
"$PY" -c 'import subprocess; s=subprocess.check_output(["nvidia-smi","--id=0","--query-gpu=memory.used,utilization.gpu","--format=csv,noheader,nounits"],text=True); m,u=map(int,s.strip().split(",")); assert m<1024 and u==0, "GPU0 busy; stop"'
"$PY" scripts/gpt_oss_qwen_100.py --config "$CONFIG" --phase prepare
"$PY" scripts/gpt_oss_qwen_100.py --config "$CONFIG" --phase run
"$PY" -c 'import json; from pathlib import Path; c=json.loads(Path("configs/gpt_oss_qwen_100_20260921.json").read_text()); r=Path(c["run_root"]); s=json.loads((r/"summary.json").read_text()); print("TECHNICAL:",s["technical_lifecycle"],"QUALITY:",s["quality_gate"]); [print(k,v["metrics"]) for k,v in s["objectives"].items()]; print("RESULT:",r/"summary.json")'
