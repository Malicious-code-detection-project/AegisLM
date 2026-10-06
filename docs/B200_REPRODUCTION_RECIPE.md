# B200 재현 레시피: 동결 v5 → 100-step 학습 → base·adapter 평가

2026-10-06 A6000 실험을 B200 한 대에서 재현한다. 사용자가 선택한 범위는
**동결된 processed 자료를 이관하고, B200에서 100-step을 새로 학습한 뒤,
동일 validation 100건으로 base와 새 adapter를 평가**하는 것이다.
코드·레시피·실험용 TOML·lock은 **Git clone**으로 가져온다.
동결 processed 자료와 감사 메타데이터는 Git 제외 정책에 따라 별도로 복사한다.
raw 전처리는 다시 수행하지 않는다.

## 1. 가져올 코드와 데이터

코드와 실행 보조 파일은 저장소의 `scripts/b200/`, 환경 선언은
`configs/environments/`, 이 문서는 `docs/`에 있다. B200에서 아래 브랜치를 clone한다.

```bash
git clone --branch experiment/b200-reproduction --single-branch \
    git@github.com:Malicious-code-detection-project/AegisLM.git
cd AegisLM
```

이미 이 브랜치가 main에 병합된 이후라면 일반 `git clone`으로 받아도 된다.
실행한 commit은 `git rev-parse HEAD`로 기록한다.

A6000에서는 동결 데이터만 묶는다. 아래 명령으로 생성되는 파일은 Git에 넣지 않는다.
이번 전달용 파일은 이미 생성해 두었으므로 다시 생성할 필요는 없다.

```bash
python3 scripts/b200/manage.py pack-data
# 생성 파일:
# outputs/b200-frozen-data-v1.tar.gz
# outputs/b200-frozen-data-v1.tar.gz.sha256
```

데이터 파일에는 train/validation, 100건 선택 목록, 기존 감사 결과와 비교용 메타데이터만
들어 있다. 코드·가상환경·모델 가중치·기존 adapter·raw·test500 본문·인증정보는 포함하지 않는다.
`configs/b200_reproduction_manifest.json`의 파일별 SHA-256으로 자료를 확인한다.
기본 모델은 아래 revision을 내려받고 adapter는 B200에서 새로 학습한다.
같은 자료와 설정을 재현하는 실험이며, GPU·커널·sampling 차이 때문에
학습된 가중치와 생성 문자열까지 A6000과 같다는 뜻은 아니다.

| 항목 | 고정 조건 |
| --- | --- |
| 기본 모델 | `unsloth/gpt-oss-20b` → `unsloth/gpt-oss-20b-unsloth-bnb-4bit` |
| HF revision | `093fba6992ef5a7152481afec0bdfca1ac486998` |
| 양자화 | 기존 Unsloth native 4bit 로딩, NF4·double quantization·BF16 compute |
| 학습 | v5 train 10,000건, `max_seq_length=1024`, `max_steps=100` |
| LoRA | r=8, alpha=16, dropout=0, bias=none, seed=3407 |
| 학습 대상 | q/k/v/o/gate/up/down projection, Unsloth gradient checkpointing |
| optimizer | adamw_8bit, LR=0.0002, batch=1, accumulation=4, warmup=5, weight_decay=0.001, linear scheduler |
| supervision | assistant JSON + 빈 `thinking`, assistant final 본문만 학습 |
| 평가 입력 | 동결 validation 100건, present 50 + not_observed 50, 입력 232–980토큰 |
| 평가 모델 | base 600회와 새 adapter 600회, 각각 독립 실행 |
| 생성 상한 순서 | 128, 512, 2048, 65536, 130000, context-minus-input |
| 평가 문맥 | 131072; 마지막 상한은 각 입력별 `131072 - input_length` |
| 생성 설정 | 원 native 기본값; generate에는 입력·max_new_tokens·streamer만 전달 |
| 프로세스 | 모델×상한마다 새 프로세스, 한 조건 100건 뒤 종료·join 후 다음 모델 로딩 |
| 실패 처리 | 첫 오류에서 해당 실행 중단, 실패 입력 건너뛰기·자동 재시도 없음 |

원 native 관측값은 sampling=True, temperature=1, top_k=50, top_p=1,
num_beams=1이다. 별도 seed 재설정·강제 EOS·final-prefill·timeout·prefill chunking을
추가하지 않는다. 긴 생성 상한이 입력 길이만큼만 메모리를 사용한다는 가정도 하지 않는다.
조건 사이의 초기화는 `empty_cache()`만 호출하는 것이 아니라 **CUDA를 소유한 프로세스의 종료**다.

## 2. clone한 저장소에 동결 데이터 복사

Linux x86_64, 사용 가능한 B200 GPU 한 대, `git`과 `uv`, 패키지·HF 다운로드 접근이 필요하다.
드라이버와 CUDA wheel의 호환성은 5절의 실제 GPU 연산으로 확인한다.

```bash
# A6000에서: B200 호스트와 clone한 저장소 경로를 실제 값으로 바꾼다.
scp outputs/b200-frozen-data-v1.tar.gz \
    outputs/b200-frozen-data-v1.tar.gz.sha256 \
    USER@B200_HOST:/ABSOLUTE/PATH/TO/AegisLM/
```

```bash
# B200에서: clone한 AegisLM 루트에서 실행한다.
sha256sum -c b200-frozen-data-v1.tar.gz.sha256
# 기존 데이터가 있다면 덮어쓰지 않고 중단한다.
tar --keep-old-files -xzf b200-frozen-data-v1.tar.gz
mkdir -p outputs/transfer
mv b200-frozen-data-v1.tar.gz b200-frozen-data-v1.tar.gz.sha256 outputs/transfer/
python3 scripts/b200/manage.py verify-data
python3 scripts/b200/manage.py init
git rev-parse HEAD > outputs/b200-source-commit.txt
```

이후 명령의 작업 디렉터리는 모두 clone한 저장소 루트다.
`init`은 절대 경로를 B200 위치에 맞게 생성하고 기존 실행이 있으면 중단한다.
새 학습 경로는 `outputs/b200-step100-v1`, 평가 경로는
`outputs/b200-{base,adapter}-validation100-v1`이다.
동결 데이터가 이미 정확히 있다면 압축 해제 대신 `verify-data`부터 실행한다.

## 3. uv TOML·lock으로 환경 설치

**freeze 파일을 설치 기준으로 사용하지 않는다.** 이번 native 실험은 루트의
training dependency group과 다른 독립 환경에서 수행됐다.
루트 lock은 torch 2.10.0 / transformers 5.5.0 / Unsloth 2026.6.9를 포함하지만,
이 실험은 torch 2.14.1 / transformers 4.56.2 / Unsloth 2026.9.14를 사용했다.
이 때문에 루트에서 `uv sync --group training`을 실행하면 같은 실험이 되지 않는다.

실제 사용한 native 113개, Harmony 11개 패키지의 버전과 Git 리비전을 각각
독립 TOML로 선언하고 `uv lock`으로 해결한 파일을 Git에서 관리한다.
설치는 `--locked`로 수행하고 설치 후 원 실행의 패키지 메타데이터와 대조한다.

```bash
uv python install 3.12.13
uv sync --locked --directory configs/environments/cc-native-step100 --python 3.12.13
uv sync --locked --directory configs/environments/cc-harmony-score --python 3.12.13
# 루트 환경은 CPU W&B tracker용이며 training group을 설치하지 않는다.
uv sync --locked --no-default-groups --python 3.12.13

configs/environments/cc-native-step100/.venv/bin/python scripts/b200/manage.py check-env native
configs/environments/cc-harmony-score/.venv/bin/python scripts/b200/manage.py check-env score
```

핵심 고정값: Python 3.12.13, Triton 3.8.0, TRL 0.22.2,
bitsandbytes 0.50.2, PEFT 0.21.2, torchao 0.18.0, tokenizers 0.22.2,
openai-harmony 0.0.8. Unsloth commit은
`5971d280d4b645c8d470d6bb3171b082c4d4d2b8`, Zoo는
`867a86383371ebeb8ab1948d085540d134c07b4c`, Triton kernels는
`0add68262ab0a2e33b84524346cb27cbb2787356`이다.

설치 실패 시 버전 범위를 풀거나 기존 GPU 환경에 섞어 설치하지 않는다.
실패 로그를 보존하고 해당 B200 환경의 호환성 문제로 분리한다.
lock 생성·기존 환경과의 일치는 확인했지만 B200 신규 설치·GPU 실행은 별도 검증 단계다.

## 4. 모델 준비와 동결 데이터 검사

모델용으로 비어 있는 전용 HF cache를 사용한다. 기존 B200 cache가 있더라도
이 실험은 아래 revision으로 맞춘다. HF 인증이 필요하면 B200에서 별도로 설정한다.

```bash
export CUDA_VISIBLE_DEVICES=0
export HF_HUB_CACHE="$PWD/outputs/b200-hf-hub"
export HF_DATASETS_CACHE="$PWD/outputs/b200-datasets-cache"
unset UNSLOTH_COMPILE_DISABLE TORCHDYNAMO_DISABLE TORCH_COMPILE_DISABLE PYTHONPATH
unset HF_HUB_OFFLINE TRANSFORMERS_OFFLINE

configs/environments/cc-native-step100/.venv/bin/python - <<'PY'
import os
from pathlib import Path
from huggingface_hub import snapshot_download
revision = "093fba6992ef5a7152481afec0bdfca1ac486998"
snapshot = Path(snapshot_download(
    "unsloth/gpt-oss-20b-unsloth-bnb-4bit", revision=revision,
    cache_dir=os.environ["HF_HUB_CACHE"],
))
assert snapshot.name == revision
# Unsloth의 revision 없는 native 로딩도 이 고정 snapshot을 찾게 한다.
ref = snapshot.parent.parent / "refs/main"
ref.parent.mkdir(parents=True, exist_ok=True)
ref.write_text(revision)
print(snapshot)
PY

# Harmony parser의 첫 초기화를 GPU 실행 전에 완료한다.
configs/environments/cc-harmony-score/.venv/bin/python - <<'PY'
from openai_harmony import HarmonyEncodingName, load_harmony_encoding
load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
print("Harmony ready")
PY

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
configs/environments/cc-native-step100/.venv/bin/python scripts/b200/train_fixed_date.py prepare \
    > outputs/b200-step100-v1/prepare.log 2>&1
configs/environments/cc-native-step100/.venv/bin/python scripts/b200/manage.py check-data
```

원 tokenizer의 chat template은 실행 날짜를 system 본문에 넣는다.
날짜가 바뀌면 학습 입력도 바뀌므로 `train_fixed_date.py`는
`apply_chat_template`의 `strftime_now` 인자만 원 실행일 `2026-10-04`로 고정한다.
원 튜토리얼 AST·마스킹·optimizer·generate는 바꾸지 않는다.
평가 스크립트도 원래부터 같은 날짜를 명시한다.

`check-data`는 training-messages SHA뿐 아니라 **10,000건 전부의 토큰 길이와
supervised-token 감사 결과**를 A6000 자료와 대조한다.
예상값은 전체 10,000, 제외 1,475, 학습 유효 8,525, 완전한 target 8,510,
부분 target 15이다. 길이 초과·원천 라벨·deprecated CWE를 이번 재현에서 수정하지 않는다.
이관한 `manifest.json`과 `split-audit.json`은 기존 전체 split 감사 기록이며,
test 본문을 새로 읽어 감사를 재실행하는 단계는 아니다.

## 5. B200에서 새 100-step 학습

아래 preflight는 짧은 BF16 행렬 연산으로 선택한 GPU를 확인하고 종료한다.
이후 학습은 별도 프로세스다. 다른 GPU 작업과 겹치지 않는지 먼저 확인한다.

```bash
nvidia-smi
configs/environments/cc-native-step100/.venv/bin/python scripts/b200/gpu_preflight.py

# SSH가 끊겨도 학습이 계속되도록 실행한다.
nohup configs/environments/cc-native-step100/.venv/bin/python -u \
    scripts/b200/train_fixed_date.py train \
    > outputs/b200-step100-v1/training.log 2>&1 < /dev/null &
echo $! > outputs/b200-step100-v1/launcher.pid
```

```bash
tail -n 30 outputs/b200-step100-v1/training.log
configs/environments/cc-native-step100/.venv/bin/python scripts/b200/manage.py check-training
```

`check-training`은 학습·adapter 저장 완료, global_step=100,
effective_records=8525, 실제 parameter 업데이트와 저장 가중치를 확인한다.
통과하기 전에는 평가를 시작하지 않는다. 새 adapter SHA는
`outputs/b200-step100-v1/b200-verification.json`에 기록되며 A6000 SHA와 같을 필요가 없다.
`training.json`, `training-runtime.json`, `training.log`가 학습 결과의 기준이다.
보존된 원 드라이버가 만드는 `results.md`의 과거 validation2건 설명은
현재 100건 평가 리포트가 아니다. 학습의 `report_to='none'`은 그대로 유지한다.

## 6. 동일 100건으로 base 먼저, adapter 다음

학습 프로세스가 종료된 뒤 **base부터** 실행한다.
각 모델은 별도 config·결과 디렉터리를 사용하므로 한쪽의 실패가 다른 쪽의
600회 계획과 결과를 섞지 않는다. 두 GPU 실행을 동시에 띄우지 않는다.

```bash
nohup bash scripts/b200/run-eval.sh base > outputs/b200-base-launch.log 2>&1 < /dev/null &
echo $! > outputs/b200-base-launcher.pid
```

base 실행 종료를 확인한 뒤 adapter를 실행한다.
base에서 오류가 나면 우선 실패 기록을 확인하고 9절 기준으로 처리한다.

```bash
cat outputs/b200-base-validation100-v1/progress.json
nvidia-smi
nohup bash scripts/b200/run-eval.sh adapter > outputs/b200-adapter-launch.log 2>&1 < /dev/null &
echo $! > outputs/b200-adapter-launcher.pid
```

`run-eval.sh`는 prepare → 6개 데이터 해시 대조 → 초기 score → GPU run → 최종 score를
순서대로 수행한다. 모델별 계획은 6조건×100=600회, 합계 1,200회다.
100건은 고정 순서 그대로이며 정답 assistant 메시지는 generate 입력에 들어가지 않는다.
평가 설정의 `new_training_steps=0`은 **평가 중 추가 학습 없음**이라는 뜻이다.
앞 단계 B200 학습은 별도로 100step 수행한다.

## 7. W&B 기록

GPU 실행과 별도인 CPU tracker를 각 평가에 하나씩 실행한다.
B200에서 `WANDB_API_KEY`와 필요시 `WANDB_ENTITY`를 환경변수 또는 루트 `.env`로 설정한다.
키를 데이터 파일이나 Git에 넣지 않는다. 원문·가중치는 tracker의 전송 대상이 아니다.

평가 prepare가 끝나 `confusion-matrices.json`이 생긴 뒤 아래를 실행한다.
파일이 아직 없으면 launch log에서 prepare 실패 여부를 확인한다.

```bash
nohup .venv/bin/python -u scripts/track_cc_native_validation100.py \
    --config configs/b200-base-validation100-v1.json --wandb \
    > outputs/b200-base-validation100-v1/tracking.log 2>&1 < /dev/null &
```

adapter 평가 시작 후에는 같은 명령의 `base`를 `adapter`로 바꿔 실행한다.
링크는 각 결과 디렉터리의 `wandb-link.json`, 기록 상태는 `wandb-progress.json`에 있다.
이 tracker는 base-only 또는 adapter-only 계획을 각각 600회로 계산한다.
W&B 상태만으로 GPU 작업의 성공·실패를 판단하지 않고 로컬 progress·receipt도 확인한다.

## 8. 결과를 읽는 기준과 완료 검사

| 파일 | 확인할 내용 |
| --- | --- |
| `outputs/b200-*-environment.json` | Python·실제 패키지 버전과 Git 리비전 |
| `outputs/b200-gpu-preflight.json` | GPU·VRAM·CUDA·드라이버·연산 성공 |
| 각 평가의 `prepared.json` | 같은 입력·gold·선택 목록, 신규 adapter SHA |
| `progress.json` | completed/planned, 현재 모델·상한, 최종 completed 또는 failed |
| `conditions/<model>-<budget>.json` | worker PID, started_at/exited_at, exitcode=0 |
| `conditions/<model>-<budget>-runtime.json` | 로딩 전 allocated/reserved=0, 로딩 후 메모리·모델 기본값 |
| `raw/*.json` | 원 generated IDs·실제 생성량·종료 사유 |
| `confusion-matrices.json` / `.md` | 완료된 결과의 strict·semantic 평가 |
| `error.json`, `conditions/*-error.json` | controller·worker의 원 오류 |

조건 A의 `exited_at` 뒤에 조건 B의 `started_at`이 오고, 각 조건이 새 worker로
실행됐는지 확인한다. 학습 프로세스도 평가 전에 종료돼 있어야 한다.
GPU 점유 프로세스가 없는지 `nvidia-smi`로 함께 확인한다.

confusion matrix의 행은 gold `present`, `not_observed`, 열은 prediction
`present`, `not_observed`, `uncertain`, `invalid` 순서다.
미실행 건은 행렬에 넣지 않고 `pending`으로 남긴다. 예컨대 completed=20이면
행렬 합계도 20이어야 하며, 나머지 80건을 TN이나 invalid로 해석하지 않는다.
초기의 0 행렬은 관측 0건이다. 생성 중 score는 첫 결과와 이후 10건 간격으로 갱신된다.

완료 조건은 각 모델 `progress.status=completed`, completed=planned=600,
6개 receipt 성공, 그룹마다 completed=100/pending=0, raw 합계 600개다.
두 모델 합계는 1,200개다. 마지막으로 결과와 설정·해시·lock 파일을 함께 보관한다.

## 9. OOM·중단·재시작

A6000 adapter 재실험은 65,536 상한의 세 번째 입력에서 OOM으로 중단됐다.
조건 시작 시 PyTorch allocated/reserved=0이 확인됐으므로, 이전 조건의 캐시 누적만으로
설명하기 어렵다. B200에서 같은 설정을 실행해 관측할 것이며 성공을 미리 보장하지 않는다.

오류 시 해당 실행의 남은 조건은 진행하지 않는다. 실패 입력을 제외하거나 생성 상한,
KV cache, attention 구현, prefill chunking을 바꿔 같은 이름으로 계속하지 않는다.
원문·traceback·메모리·완료 개수를 보존한다. 이미 별도 계획으로 준비된 다른 모델은
실패 프로세스 종료를 확인하고 원인에 공통 환경 문제가 없는지 검토한 뒤 실행한다.

조건 중간에 중단된 결과에 append하면 native sampling의 RNG 경로가 달라진다.
따라서 `run-eval.sh`는 이미 준비된 출력에 재실행하지 않는다.
기존 runner도 interrupted condition을 거부한다. 재시도가 필요하면 원인을 기록하고
새 experiment ID·config·출력 경로로 별도 실험을 만든다. 완료 결과를 지워 재사용하지 않는다.

## 10. 재현 근거와 범위

동결 자료를 쓰는 이유는 raw 전처리기가 과거 processed 제외 목록·fingerprint와
정규화 cache에도 의존하기 때문이다. 또한 DecompileBench ID 수정 이후 현재 raw builder는
과거 빌드와 달라질 수 있다. raw만 다시 처리하고 같은 cohort라고 간주하지 않는다.

대조 기준은 `data/reproduction/b200-step100-v1/evaluation-prepared.json`의 다음 6개 SHA다.
adapter SHA만 B200 새 학습 결과로 교체한다.

| 대상 | SHA-256 |
| --- | --- |
| train | `b2827d06416fc256811bd6b3b662ff143d0f52604891856620153b2a1ec3e83f` |
| validation | `564fea1dabe56b90e1ab0b8cec0f4841dbbbe7578aaaafbb091863caef86238c` |
| 100건 selection | `5212df2279adff873137f0b1180d47afa003be6ce58dc6e8552c6a9180457a2a` |
| frozen input IDs | `abe9c5992f5764a6c270e80e83e29febf28b267daaffc89a3af8c5c040163135` |
| prompts | `6590d418ce674d7ff3475c99c796a0e2c147fcfa6d7ef4baa00dc45871726f1c` |
| gold | `fb1b84c94a7e4cb80a072099b8336591d48128c6a6d823278845855d3cde5d9f` |

원 학습 기준은 [100-step 실행 기록](FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-official-tutorial-v5-max-steps-100),
평가·OOM 해석은 [GPT-OSS 오류 분석](GPT_OSS_SERVING_TRAINING_ERROR_ANALYSIS.md),
processed 계보는 [데이터 아티팩트 목록](DATASET_ARTIFACT_INVENTORY.md)에 있다.
이 문서는 실행에 필요한 내용을 포함하며 해당 문서를 추가로 읽어야 실행되는 구조는 아니다.

작성 시 검증: 두 환경의 `uv lock --check --offline` 통과, 기존 native 113개·scorer
11개 패키지와 lock의 버전·Git revision 일치, 임시 디렉터리로 이관 후 학습 prepare
및 10,000건 mask 감사 일치, base/adapter 양쪽 평가 prepare의 6개 데이터 SHA 일치,
Harmony 초기 score의 모델별 600건 pending 확인, 실행 보조 파일 문법 검사 통과.
이 CPU 검증의 adapter 파일은 해시 경로만 검사하는 명시적 가짜 파일이며 모델로
로딩하지 않았다. 검증용 가짜 파일·실행 디렉터리는 Git과 데이터 전송 파일에 포함하지 않는다.
B200 신규 설치·100step 학습·1,200회 생성의 성공은 아직 검증하지 않았다.

Git 전달 전 검사: pytest 577개, Ruff lint·format, mypy 통과.
복제 경로에 맞춘 초기화, 기존 실행 보존, 데이터 변조 거부, 데이터 전용 export,
미완료 학습 거부를 CPU 회귀 테스트로 확인한다.
