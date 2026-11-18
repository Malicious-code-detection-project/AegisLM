#!/usr/bin/env bash
set -euo pipefail
# 호출 위치에 관계없이 프로젝트 루트에서 상대 경로를 해석한다.
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
# 기존 B200 캐시·실행 환경을 읽고, Python 코드가 모델별 GPU를 선택한다.
source outputs/b200-runtime-env.sh
# exec로 셸을 교체해 tmux의 중단 신호가 실행 관리 Python에 직접 전달되게 한다.
exec configs/environments/cc-native-step100/.venv/bin/python scripts/b200/evaluate.py "$@"
