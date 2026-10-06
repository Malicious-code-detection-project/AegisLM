# 독립 실험 환경

2026-10-04 공식 튜토리얼 100step 실험은 루트 `pyproject.toml`의 training group과
다른 가상환경을 사용했다. B200 이관 시 현재 루트 lock으로 그 환경을 대체하지 않는다.

- `cc-native-step100`: 실제 native 환경의 113개 패키지 버전과 Unsloth·Zoo·Triton kernels Git 리비전.
- `cc-harmony-score`: 실제 Harmony scorer 환경의 11개 패키지 버전.

각 디렉터리의 `pyproject.toml`이 선언, `uv.lock`이 해결된 설치 기준이다.
이 파일들은 기존 환경을 변경하지 않고 생성했으며, 기록된 패키지 버전과 lock을 대조했다.
과거의 전이 의존성도 실험 환경 보존을 위해 명시적으로 고정했다.
루트와 독립된 Linux x86_64 / Python 3.12 프로젝트이며 workspace member가 아니다.

```bash
uv sync --locked --directory configs/environments/cc-native-step100 --python 3.12.13
uv sync --locked --directory configs/environments/cc-harmony-score --python 3.12.13
```

설치 후 검증·모델 revision·데이터·학습·평가 명령은
[B200 재현 레시피](../../docs/B200_REPRODUCTION_RECIPE.md)를 따른다.
새 패키지 조합을 시험할 때는 이 기준을 덮어쓰지 말고 별도 실험 환경으로 분리한다.
