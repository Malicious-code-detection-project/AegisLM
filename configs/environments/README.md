# 독립 실험 환경

2026-10-04 공식 튜토리얼 100step 실험은 루트 `pyproject.toml`의 training group과
다른 가상환경을 사용했다. B200 이관 시 현재 루트 lock으로 그 환경을 대체하지 않는다.

- `cc-native-step100`: 실제 native 환경의 113개 패키지 버전과 Unsloth·Zoo·Triton kernels Git 리비전.
- `cc-harmony-score`: 실제 Harmony scorer 환경의 11개 패키지 버전.

각 디렉터리의 `pyproject.toml`이 선언, `uv.lock`이 해결된 설치 기준이다.
이 파일들은 기존 환경을 변경하지 않고 생성했으며, 기록된 패키지 버전과 lock을 대조했다.
과거의 전이 의존성도 실험 환경 보존을 위해 명시적으로 고정했다.
루트와 독립된 Linux x86_64 / Python 3.12 프로젝트이며 workspace member가 아니다.

## B200 설치: Python 3.12.3

원 A6000 실행의 Python은 **3.12.13**이다. 외부에서 관리하는 B200 서버에서는
**3.12.3**을 사용하도록 합의했으며, 2026-10-08 조회한 두 가상환경 모두 이 버전이다.
두 프로젝트의 Python 선언은 `>=3.12,<3.13`이고 기존 패키지 버전·Git revision·lock은 유지한다.
아래는 B200 설치 명령이며, A6000의 원 Python 패치까지 재현할 때는 3.12.13을 사용한다.

```bash
uv sync --locked --directory configs/environments/cc-native-step100 --python 3.12.3
uv sync --locked --directory configs/environments/cc-harmony-score --python 3.12.3
```

가상환경은 각각 `cc-native-step100/.venv`와 `cc-harmony-score/.venv`에 있다.
현재 B200에는 두 환경이 이미 설치되어 있으므로 이 문서 수정만으로 다시 설치할 필요는 없다.
B200 환경 검사는 `--expected-python 3.12.3`을 명시하는 재현 레시피와 launcher를 따른다.
Python 패치 차이는 원 환경과의 차이로 기록하며, 패키지 대조 검사는 유지한다.

## 가상환경 활성화와 전환

아래 명령은 B200 Linux의 프로젝트 루트에서 실행한다.

학습·응답 생성용 환경 활성화:

```bash
source configs/environments/cc-native-step100/.venv/bin/activate
python --version
```

작업 후 현재 환경을 해제하고 CPU 채점용 환경으로 전환:

```bash
deactivate
source configs/environments/cc-harmony-score/.venv/bin/activate
python --version
```

활성화된 가상환경에서 나가기:

```bash
deactivate
```

현재 B200에서는 두 환경 모두 Python 3.12.3으로 표시된다. 활성화는 현재 shell에서 사용할
Python을 선택하는 작업이다. 두 GPU 학습은 B200 재현 레시피의 DDP launcher를 따른다.
제공된 B200 실행 스크립트는 환경별 Python 경로를 직접 사용하므로, 해당 스크립트를
실행할 때 가상환경을 수동으로 활성화할 필요는 없다.

설치 후 검증·모델 revision·데이터·학습·평가 명령은
[B200 재현 레시피](../../docs/B200_REPRODUCTION_RECIPE.md)를 따른다.
새 패키지 조합을 시험할 때는 이 기준을 덮어쓰지 말고 별도 실험 환경으로 분리한다.
