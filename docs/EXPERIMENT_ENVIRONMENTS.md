# 장비별 실험 환경 기준

이 문서는 `AegisLM`과 별도 연구 저장소 `AegisLM_Architecture`([관련 저장소와 경계](RELATED_REPOSITORIES.md))가 쓰는 장비별 실험 환경을 같은 항목으로 기록한다. 두 저장소가 같은 모델(GPT-OSS-20B)과 같은 장비를 쓰므로, 결과를 비교하기 전에 소프트웨어 버전 차이를 먼저 확인하기 위한 기준이다.

- 독립 실험 환경의 선언과 lock은 [configs/environments/README.md](../configs/environments/README.md), B200 설치·실행 절차는 [B200 재현 레시피](B200_REPRODUCTION_RECIPE.md)를 따른다.
- 이 문서는 관측한 상태를 기록한다. 환경을 바꾸는 기준이 아니며, 버전을 맞추려고 기존 환경을 덮어쓰지 않는다.
- 같은 장비라도 환경(venv)이 다르면 결과를 장비 효과로 단정하지 않는다. 결과마다 아래 수집 항목을 함께 남긴다.

## 1. 장비

| 항목 | A6000 (2026-10-22 확인) | B200 ([B200 실험표](B200_EXPERIMENT_TABLES.md) 기록, 2026-10-07 조회) |
| --- | --- | --- |
| OS | Ubuntu 24.04.4 LTS | 미기록 |
| Kernel | 7.0.0-38-generic | 미기록 |
| NVIDIA 드라이버 | 595.99.02 | 580.95.05 |
| GPU | RTX A6000 1개, 49,140 MiB, VBIOS 94.02.5C.00.02 | B200 2개, 각 183,359 MiB, CUDA capability 10.0 |
| CPU / RAM | Xeon w5-3435X 32 threads / 125 GiB | 미기록 |
| 시스템 `nvcc` | 12.0 (torch wheel은 자체 CUDA 런타임을 사용) | 미기록 |
| uv | 0.11.14 | 미기록 |

**A6000 드라이버 기록.** 2026-10-11 `unattended-upgrade`가 사용자 공간 드라이버를 595.84에서 595.99.02로 올렸으나 재부팅 전까지 595.84 커널 모듈이 남아 `nvidia-smi`와 NVML이 `Driver/library version mismatch`로 실패했다. 이 기간(2026-10-11 ~ 2026-10-21 재부팅)의 GPU 실행 기록에는 NVML 경고가 있을 수 있다. 2026-10-21 재부팅 후 커널 모듈 595.99.02, `nvidia-smi`, PyTorch CUDA 연산이 정상임을 확인했다. 재부팅 시 kernel도 7.0.0-34에서 7.0.0-38로 바뀌었고 DKMS 모듈은 두 kernel 모두 설치돼 있다.

## 2. Python 환경

A6000에는 패키지 조합이 다른 두 계열의 환경이 있다(2026-10-22 확인).

- **루트 계열 (torch 2.10.0 / transformers 5.5.0).** `AegisLM/.venv`, `AegisLM_Architecture/.venv`, `experiments/training-loop-debug/.venv`가 같은 패키지 조합이다. 두 저장소의 `uv.lock`은 147개 항목 중 프로젝트 자신의 이름(`aegislm` / `aegislm-architecture`)만 다르고 외부 패키지 146개의 버전이 모두 같다. 두 저장소 `.venv` 모두 `uv sync --locked --dry-run --all-groups`에서 변경 없음으로 lock과 일치했다.
- **native 계열 (torch 2.14.1 / transformers 4.56.2).** `experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv`다. `uv pip freeze` 결과 113개 패키지가 `configs/environments/cc-native-step100/uv.lock`과 모두 같다(lock의 추가 1개는 프로젝트 자신). [A6000 실험표](A6000_EXPERIMENT_TABLES.md)의 native 30/100-step과 B200 100-step 재현이 이 패키지 조합을 쓴다.

| 패키지 | A6000 루트 계열 (`AegisLM/.venv` = `AegisLM_Architecture/.venv`) | A6000 native 계열 = `cc-native-step100` lock | B200 native (B200 실험표 기록) |
| --- | --- | --- | --- |
| Python | 3.12.13 | 3.12.13 | 3.12.3 (외부 관리 서버, 차이 승인·기록) |
| torch | 2.10.0 (CUDA 12.8, cuDNN 91002) | 2.14.1 (CUDA 13.0, cuDNN 92400) | 2.14.1 (CUDA 13.0) |
| transformers | 5.5.0 | 4.56.2 | 4.56.2 |
| peft | 0.19.1 | 0.21.2 | 0.21.2 |
| trl | 0.24.0 | 0.22.2 | 0.22.2 |
| accelerate | 1.14.0 | 1.15.0 | 1.15.0 |
| bitsandbytes | 0.49.2 | 0.50.2 | 0.50.2 |
| unsloth / unsloth_zoo | 2026.6.9 / 2026.6.7 | 2026.9.14 / 2026.9.9 | 2026.9.14 / 2026.9.9 |
| datasets | 4.3.0 | 4.8.5 | 미기록 |
| huggingface_hub | 1.31.0 | 0.36.2 | 미기록 |
| triton | 3.6.0 | 3.8.0 | 3.8.0 |
| torchao | 0.18.0 | 0.18.0 | 0.18.0 |
| tokenizers | 0.22.2 | 0.22.2 | 미기록 |
| `uv.lock` SHA256 | `8d80a4a0…567ad81` (`AegisLM`), `b9b0398b…bdc450a` (`AegisLM_Architecture`) | `c1bec127…eb09af7` | 미기록 (native 113개 패키지 버전을 원 기록과 대조) |

- B200 열은 B200 실험표의 기록값이다. 그 표가 적지 않은 항목(OS, kernel, lock 해시 등)은 미기록으로 두고 4절의 수집으로 채운다. B200은 torchao 0.18.0을 포함한다.
- `cc-harmony-score`(lock `043c09ea…54d054`, `openai-harmony` 0.0.8 등 12개)는 채점 전용 환경이며 A6000에는 설치돼 있지 않다.
- A6000의 두 계열 모두 `kernels`, `flash-attn`, `openai-harmony`가 없다.
- `AegisLM_Architecture`의 A6000 실험(B0–B3 검증, 메모리 기법 탐색)은 루트 계열에서 실행됐다. 같은 장비에 B200과 같은 native 계열이 있으므로, 장비 효과를 소프트웨어 버전과 분리하려면 native 계열에서의 A6000 실행을 비교 후보로 둘 수 있다(미실행 제안).

**확인이 필요한 불일치.** `AegisLM_Architecture`의 `A6000_PLAN.md`는 B200 환경의 `uv.lock` SHA256을 `8d80a4a0…`로 적었다(사용자 조회, 2026-10-20). 이 값은 `AegisLM` 루트 lock의 해시이며 `cc-native-step100` lock(`c1bec127…`)과 다르다. 같은 표의 B200 패키지 버전(torch 2.14.1+cu130, transformers 4.56.2)은 `cc-native-step100`과 B200 실험표에 맞는다. B200에서 실제로 사용한 venv와 그 lock을 4절 수집으로 확정한다.

## 3. 모델 revision

두 저장소는 같은 HF 캐시(`~/.cache/huggingface/hub`)를 읽는다. A6000 캐시에는 다음 두 snapshot만 있다.

| 모델 | revision | 사용처 |
| --- | --- | --- |
| `openai/gpt-oss-20b` | `6cee5e81ee83917806bbde320786a8fb61efebee` | `AegisLM_Architecture` B0–B3 출발 모델 |
| `unsloth/gpt-oss-20b-unsloth-bnb-4bit` | `093fba6992ef5a7152481afec0bdfca1ac486998` | `AegisLM` 기존 Unsloth SFT |

## 4. 수집 절차 (A6000·B200 공통)

장비마다 같은 명령으로 수집하고 결과를 이 문서의 표에 옮긴다. 수집은 읽기 전용이며 패키지를 설치하거나 바꾸지 않는다. 출력에서 개인 경로·계정·토큰을 지운 뒤 기록한다.

```bash
# 장비
lsb_release -ds; uname -r
head -1 /proc/driver/nvidia/version
nvidia-smi --query-gpu=name,memory.total,driver_version,vbios_version --format=csv,noheader
lscpu | grep 'Model name'; nproc; free -g | awk 'NR==2{print "RAM", $2"G"}'
uv --version

# 환경별 패키지: 실제로 학습·평가에 쓰는 각 venv의 python으로 실행한다.
PY=configs/environments/cc-native-step100/.venv/bin/python   # 환경마다 바꿔 실행
"$PY" -I - <<'PY'
import importlib.metadata as m, json, platform
names = ["torch", "transformers", "peft", "trl", "accelerate", "bitsandbytes", "unsloth",
         "unsloth_zoo", "datasets", "tokenizers", "safetensors", "huggingface_hub",
         "triton", "torchao", "kernels", "flash-attn", "openai-harmony"]
out = {"python": platform.python_version()}
for name in names:
    try:
        out[name] = m.version(name)
    except m.PackageNotFoundError:
        out[name] = None
import torch
out.update({"torch.cuda": torch.version.cuda, "cudnn": torch.backends.cudnn.version(),
            "cuda_available": torch.cuda.is_available(), "gpus": torch.cuda.device_count()})
print(json.dumps(out, indent=1))
PY

# lock 해시와 venv-lock 일치 (변경 없이 확인만)
sha256sum uv.lock configs/environments/*/uv.lock
uv sync --locked --dry-run --directory configs/environments/cc-native-step100

# 모델 snapshot
for r in ~/.cache/huggingface/hub/models--*gpt-oss*; do echo "$(basename "$r"): $(ls "$r/snapshots")"; done
```

## 5. 운영 규칙

- A6000 GPU는 한 장을 두 저장소가 함께 쓴다. 실행 전 `nvidia-smi`로 다른 저장소의 GPU 프로세스가 없는지 확인한다.
- 드라이버 자동 업데이트 뒤에는 재부팅 전까지 GPU 실행 결과를 신뢰하지 않는다. 장기 실험 중에는 NVIDIA 패키지 `apt-mark hold`를 검토한다(현재 미적용).
- 환경 버전을 맞출 필요가 생기면 기존 venv를 바꾸지 않고 `configs/environments/` 아래에 새 독립 환경을 만든다.
- 실험 결과 기록에는 장비, venv 경로(저장소 기준 상대 경로), lock SHA256, 모델 revision, 커널 모듈 버전을 함께 남긴다.
