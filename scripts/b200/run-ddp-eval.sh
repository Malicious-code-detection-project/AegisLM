#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
# kind는 평가 모델 종류, run은 이미 학습·저장을 끝낸 DDP 실행 이름이다.
kind=${1:?Pass base or adapter}
run=${2:?Pass the completed two-GPU training run name}
case "$kind" in base|adapter) ;; *) exit 2 ;; esac
# 기존 개별 모델 명령을 새 실행 관리 코드로 연결한다. GPU 미지정 시 원 기본값 0이다.
exec bash scripts/b200/run-evaluation.sh run --run "$run" --models "$kind" --gpus "${B200_EVAL_GPU:-0}"
