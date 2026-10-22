# 관련 저장소와 경계

`AegisLM`과 별도 연구 저장소 `AegisLM_Architecture`의 역할, 주고받는 산출물, 공유 자원 규칙을 정한다. 두 저장소는 같은 모델(GPT-OSS-20B), 같은 장비(A6000, B200), 같은 과제 영역(C/C++ 취약 판정, CWE)을 다루지만 운영 방식이 다르므로 합치지 않는다. 2026-10-22 사용자 결정이다.

## 1. 역할

한 줄 기준은 **파이프라인과 제품은 `AegisLM`, 구조와 학습 위치 연구는 `AegisLM_Architecture`**다. "파인튜닝을 하느냐"로 나누지 않는다. `AegisLM_Architecture`의 B1–B3도 SFT다.

| | `AegisLM` (파인튜닝 프로젝트) | `AegisLM_Architecture` (아키텍처 프로젝트) |
| --- | --- | --- |
| 질문 | 보안 분석 모델을 어떻게 쓸 만하게 만드는가 | 어디를, 어떤 구조로 학습해야 효과적인가 |
| 범위 | 데이터 수집·정제, prompt contract, LoRA/QLoRA 학습, 평가 harness, 추론 파이프라인, Project NuriLab 전달 | 블록 선택 학습·블록 추가(B0–B3), 학습 대상·구조 비교, 통제 실험, 논문 원고 |
| SFT의 위치 | 파이프라인의 본 작업 | 비교 실험의 한 갈래(B1–B3) |
| 운영 | 팀 저장소, Phase A–G, PR 템플릿·품질 게이트([CONTRIBUTING](CONTRIBUTING.md), [QUALITY_GATES](QUALITY_GATES.md)) | 개인 연구 저장소(private), 연구노트·원고 규칙, 원고와 연구 기록은 맥북 기준 편집 |

**Phase G.** README 로드맵의 Phase G(직접 모델/레이어 연구)는 `AegisLM_Architecture`에서 수행한다. `AegisLM`에 별도 구조 연구 코드를 만들지 않으며, 구조 연구를 위해 저장소를 더 나누지 않는다. `AegisLM_Architecture`의 결과 중 쓸 만한 구조나 adapter를 이 저장소의 파이프라인에 들여오는 작업은 `AegisLM`의 몫이며, 들여올 때 이 저장소의 schema·평가 기준으로 다시 검증한다.

## 2. 주고받는 산출물

두 저장소는 서로의 파일 경로를 직접 읽지 않는다. 필요한 것은 동결한 기록으로 주고받는다.

| 방향 | 무엇 | 형식 |
| --- | --- | --- |
| `AegisLM` → Architecture | B1 기준선에 쓸 SFT 조건(데이터 ID 목록·순서, seed, LoRA·optimizer 설정, prompt·loss mask, 토큰 예산) | manifest: `AegisLM` commit, config 경로, 데이터 파일 SHA256, 사용한 venv의 `uv.lock` SHA256, 모델 revision |
| `AegisLM` → Architecture | 장비별 실험 환경 | [장비별 실험 환경](EXPERIMENT_ENVIRONMENTS.md) |
| Architecture → `AegisLM` | 채택할 구조·학습 위치와 근거 | Architecture commit, 결과 보고서 경로, 모델 revision, 재현 조건 |

manifest 대신 값을 문서에 손으로 옮겨 적으면 어긋나기 쉽다. 2026-10-22에 B200 lock 해시가 다른 lock의 값으로 기록된 사례가 있다([장비별 실험 환경](EXPERIMENT_ENVIRONMENTS.md) 2절).

## 3. 정본

같은 자료가 두 저장소에 있으면 정본을 하나로 정하고 다른 쪽은 버전과 해시로 참조한다.

| 자료 | 현재 상태 | 정본 |
| --- | --- | --- |
| CWE 참조 | `AegisLM`: `scripts/cwe_reference.py`와 영문 CWE 사전 / Architecture: `data/taxonomy/cwe-4.20` | **미정.** 통일에는 합의했고, B200과 맞춘 뒤 정한다 |
| 실험 환경 lock | A6000 두 저장소의 루트 lock은 외부 패키지가 같고, native 계열은 `configs/environments/cc-native-step100` | 독립 실험 환경은 `configs/environments/`, 장비별 관측은 [장비별 실험 환경](EXPERIMENT_ENVIRONMENTS.md) |
| GPT-OSS-20B 가중치 | 공용 HF 캐시 | HF revision (`openai/gpt-oss-20b` `6cee5e81…`, `unsloth/gpt-oss-20b-unsloth-bnb-4bit` `093fba69…`) |

## 4. 공유 자원

- A6000 GPU는 한 장을 두 저장소가 함께 쓴다. 실행 전 `nvidia-smi`로 다른 저장소의 GPU 프로세스가 없는지 확인한다.
- HF 캐시(`~/.cache/huggingface/hub`)는 공용 읽기 자원으로 다룬다. 한 저장소의 작업이 snapshot을 지우거나 바꾸지 않는다.
- 실행 출력(`runs/`, `outputs/` 등)은 각 저장소 안의 Git 제외 경로에 둔다.
- 에이전트 세션은 작업할 저장소의 루트에서 연다. 그래야 그 저장소의 AGENTS.md·CLAUDE.md가 적용된다.
