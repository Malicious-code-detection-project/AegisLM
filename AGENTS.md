# AGENTS.md - AegisLM Collaboration Manual

이 문서는 `AegisLM` 저장소에서 코드를 작성하는 모든 주체가 따르는 협업 운영 규칙이다. 사람, Codex, Claude Code, Cursor, 기타 코딩 에이전트는 이 문서를 기준으로 작업한다.

`AegisLM`은 Project NuriLab과 연계할 수 있는 별도 LLM 모델 개발 프로젝트다. 이 저장소의 책임은 보안 분석 특화 LLM의 학습, 데이터셋 구성, 평가, 추론 검증, adapter 개선, 장기적인 모델 구조 연구다.

Project NuriLab과 협업 방식과 보안 철학은 공유하지만, 이 저장소는 Project NuriLab의 내부 구현 모듈이 아니다.

---

## 1. 시작 전 필독 - SSOT 지도

| 알고 싶은 것 | 정본 위치 |
| --- | --- |
| 프로젝트 정체성, 현재 단계, 전체 로드맵 | `README.md` |
| 파인튜닝 학습 로드맵과 실험 전략 | `FINETUNING_EXPERIMENT_PLAN.md` |
| 팀 기여 절차, 브랜치, 커밋, 검증 규칙 | `CONTRIBUTING.md` |
| 에이전트/개발자 공통 운영 규칙 | `AGENTS.md` |
| Python 패키지 설정 | `pyproject.toml` |
| 테스트 | `tests/` |

**규칙 0 - 현황을 단정하기 전에 동기화한다.**

작업 전에는 로컬 브랜치와 원격 상태를 확인한다.

```bash
git fetch origin
git status
```

로컬 상태가 뒤처진 채로 "없다", "미구현이다", "충돌 없다"라고 단정하지 않는다.

---

## 2. 프로젝트 방향

이 프로젝트의 목표는 보안 분석에 특화된 로컬 LLM을 학습, 평가, 개선하는 것이다.

현재 README의 Phase A-G 로드맵을 기준으로 진행한다.

```text
Phase A: 문서/저장소 정체성 정리
Phase B: 최소 코드 뼈대 생성
Phase C: JSON schema + tiny dataset
Phase D: baseline inference + evaluation
Phase E: tiny SFT PoC
Phase F: dataset 확장 + adapter 개선
Phase G: 직접 모델/레이어 연구
```

현재 Phase B의 우선순위는 다음과 같다.

- 데이터, 평가, 학습, 추론의 최소 scaffold 설계
- 코드 패키지, scripts, configs, tests, experiments 디렉터리 생성
- raw dataset, checkpoint, adapter artifact가 Git에 들어가지 않도록 안전장치 정리
- 실제 학습 방식 선택은 Phase B 이후로 보류

---

## 3. 작업 선택 규칙

작업은 자유롭게 선택하되, 다음 순서를 지킨다.

```text
문서/정체성 정리
-> 저장소 scaffold 설계
-> schema와 prompt contract 정의
-> tiny dataset 준비
-> baseline inference 확인
-> evaluation 구현
-> tiny SFT PoC
-> adapter 개선과 dataset 확장
```

착수 전 체크리스트:

- [ ] 작업 목적이 README의 Phase A-G 로드맵과 맞는가?
- [ ] 같은 작업을 다른 사람이 진행 중이지 않은가?
- [ ] 데이터, 모델, checkpoint, adapter 저장 위치가 Git 밖으로 분리되는가?
- [ ] schema, dataset format, prompt contract, evaluation 기준에 영향이 있는가?
- [ ] 영향이 있다면 테스트와 문서 갱신 계획이 있는가?

의존성이 있는 작업은 상위 작업을 먼저 끝낸다.

- 학습 스크립트 전: schema와 tiny dataset 확인
- adapter 학습 전: baseline inference와 evaluation 확인
- dataset 확장 전: 안전/저장 정책 확인
- 모델 구조 연구 전: LoRA / QLoRA 한계와 평가 목표 확인

---

## 4. 네이밍 표준

모든 브랜치, 커밋, PR은 작업 목적을 드러내야 한다.

| 대상 | 형식 | 예시 |
| --- | --- | --- |
| 문서 브랜치 | `docs/<topic>` | `docs/project-identity` |
| 기능 브랜치 | `feat/<topic>` | `feat/scaffold-training-layout` |
| 실험 브랜치 | `experiment/<topic>` | `experiment/tiny-sft-poc` |
| 테스트 브랜치 | `test/<topic>` | `test/evaluation-json-contract` |
| 버그 브랜치 | `fix/<topic>` | `fix/dataset-validator` |
| 커밋 | `<type>: <summary>` | `docs: define model development roadmap` |
| PR 제목 | `[AegisLM] <summary>` | `[AegisLM] Add tiny SFT evaluation harness` |

`<type>`은 다음 중 하나를 사용한다.

- `feat`
- `fix`
- `docs`
- `test`
- `refactor`
- `chore`
- `experiment`

커밋 메시지는 Conventional Commits 형식을 권장한다.

---

## 5. 개발 가드레일

**Must Do**

- 작은 단위로 변경한다.
- 데이터, 평가, 학습, 추론 책임을 분리한다.
- public 함수와 주요 데이터 모델에는 타입 힌트를 유지한다.
- schema, prompt contract, dataset format 변경은 문서와 테스트를 함께 갱신한다.
- 학습 전 baseline inference와 evaluation 기준을 먼저 마련한다.
- 모델, adapter, checkpoint, raw dataset은 Git 저장소 밖에 둔다.
- 실험 결과는 재현 가능하도록 package version, command, dataset path, GPU 정보를 기록한다.

**Must Not**

- 실제 악성 샘플, secrets, API key, private CTI, 민감 데이터를 커밋하지 않는다.
- raw dataset, model checkpoint, adapter artifact를 커밋하지 않는다.
- `main`에 직접 push하지 않는다.
- LLM 응답을 최종 보안 판단 기준으로 삼지 않는다.
- 공격 실행 절차, 우회 로직, credential theft workflow를 학습 데이터로 만들지 않는다.
- 평가 기준 없이 대형 학습부터 시작하지 않는다.
- v0에서 직접 model architecture 변경을 시작하지 않는다.

**판단 기준**

- 모델은 설명, 요약, TTP 매핑, 우선순위화, 구조화된 보고 출력을 담당한다.
- 판단 근거는 deterministic evidence, curated labels, human review, evaluation result를 기준으로 한다.
- fine-tuning 성공 여부는 loss만이 아니라 JSON 유효성, 필드 완성도, 안전성, hallucination rate로 평가한다.

---

## 6. 코드 구조와 책임

Phase B 이후의 기본 책임 경계는 다음을 목표로 한다.

| 영역 | 책임 |
| --- | --- |
| `aegislm/schemas.py` | JSON output contract, dataset record shape |
| `aegislm/prompts/` | system/user prompt template |
| `aegislm/datasets/` | dataset formatting, validation, split helpers |
| `aegislm/evaluation/` | JSON validity, required fields, safety checks |
| `aegislm/inference/` | base model and adapter inference helpers |
| `aegislm/training/` | TRL / Unsloth training helpers |
| `scripts/` | one-command entrypoints for dataset, inference, train, evaluate |
| `configs/` | baseline and tiny SFT experiment configs |
| `tests/` | schema, dataset, evaluation regression tests |

새 모듈을 만들기 전에 기존 책임 경계에 들어갈 수 있는지 먼저 확인한다. 단일 사용처를 위한 추상화는 만들지 않는다.

---

## 7. 테스트 규칙

문서만 바꾸는 작업은 별도 코드 테스트가 필요하지 않다.

코드가 추가된 뒤 PR 전에는 가능한 범위에서 다음을 실행한다.

```bash
uv run python -m unittest discover -s tests
uv run ruff check .
```

변경 영역별 테스트 기준:

- schema 변경: JSON contract와 required field 테스트
- dataset 변경: dataset record validation, split, unsafe sample exclusion 테스트
- prompt 변경: formatting snapshot 또는 expected message shape 테스트
- evaluation 변경: invalid JSON, missing fields, hallucinated mapping, unsafe guidance 테스트
- training helper 변경: config parsing과 dry-run 가능한 단위 테스트
- inference helper 변경: mock model 또는 fixture output 기반 테스트

실제 GPU, 대형 모델, 외부 dataset이 필요한 검증은 일반 PR 필수 테스트로 만들지 않는다. 그런 검증은 별도 experiment log에 기록한다.

---

## 8. PR 제출 체크리스트

PR 생성 전:

- [ ] 최신 `main` 기준 브랜치에서 작업했는가?
- [ ] 브랜치명이 네이밍 표준을 따르는가?
- [ ] PR 제목이 `[AegisLM] <summary>` 형식을 따르는가?
- [ ] 문서 변경만인지, 코드 변경인지 명확한가?
- [ ] 코드 변경이면 관련 테스트를 추가하거나 갱신했는가?
- [ ] 가능한 경우 `uv run python -m unittest discover -s tests` 통과
- [ ] 가능한 경우 `uv run ruff check .` 통과
- [ ] schema, dataset format, prompt contract 변경 시 README 또는 실험 계획을 갱신했는가?
- [ ] raw dataset, checkpoint, adapter artifact, secrets, 민감 데이터가 포함되지 않았는가?
- [ ] 실험 결과를 주장한다면 command, package version, GPU, dataset path를 기록했는가?

PR 본문에는 다음을 포함한다.

- 변경 목적
- 주요 변경 내용
- 검증 명령과 결과
- 제한사항 또는 후속 작업
- 관련 GitHub Issue

---

## 9. 거버넌스

- `README.md`는 프로젝트 정체성, 현재 단계, 전체 로드맵의 정본이다.
- `FINETUNING_EXPERIMENT_PLAN.md`는 학습 로드맵, 실험 전략, dataset/evaluation 기준의 정본이다.
- `AGENTS.md`는 작업 규칙과 에이전트 행동 기준의 정본이다.
- `CONTRIBUTING.md`는 팀원이 PR을 올리기 위한 절차 문서다.
- GitHub Issue는 작업 단위와 상태 추적의 정본이다.
- PR은 코드 리뷰와 변경 이력의 정본이다.

schema, dataset format, prompt contract, evaluation metric, artifact storage policy 변경은 반드시 문서와 테스트를 함께 갱신한다.

모호하거나 막히면 임의로 확장하지 말고 GitHub Issue 또는 PR 코멘트에 남긴 뒤 Owner 확인을 받는다.

---

## 10. 유지보수 TODO

- Phase B scaffold 구조 확정
- GitHub Issue template과 PR template 추가
- GitHub Actions 기반 문서/테스트 CI 검토
- raw dataset, checkpoint, adapter artifact 저장 정책 구체화
- experiment log template 추가
- CODEOWNERS 도입 여부 검토
- branch protection 설정 검토
