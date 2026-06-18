# Contributing Guide

이 문서는 `AegisLM`에 기여하는 팀원이 작업을 시작하고, 브랜치를 만들고, PR을 제출하기 위해 따라야 하는 절차를 정리합니다.

협업 규칙의 정본은 [AGENTS.md](../AGENTS.md)입니다. 이 문서는 팀원이 실제로 작업을 진행할 때 참고하는 실행 가이드입니다.

---

## 프로젝트 한 줄 요약

`AegisLM`은 Project NuriLab과 연계할 수 있는 별도 LLM 모델 개발 프로젝트입니다.

이 저장소는 보안 분석 시스템 자체를 구현하지 않습니다. 로컬 LLM 파인튜닝, 보안 분석 특화 데이터셋 구성, JSON 구조화 출력 학습, evaluation harness, adapter 개선, 장기적인 모델 구조 연구를 담당합니다.

현재 단계는 README의 **Phase D: baseline inference + evaluation**입니다. Phase C의 데이터 전략, JSON schema, tiny fixture, validation baseline은 완료되었고, 파인튜닝 전 baseline inference와 evaluation 기준선을 먼저 확인합니다. Phase E 착수 여부는 [PHASE_D_EXIT_CRITERIA.md](PHASE_D_EXIT_CRITERIA.md)의 gate로 판단합니다.

---

## 작업 재개 절차

새 PC에서 작업하거나 오랜만에 저장소를 열었다면 아래 순서로 확인합니다.

1. [README.md](../README.md) - 프로젝트 정체성, 현재 단계, Phase A-G 로드맵
2. [DATA_STRATEGY.md](DATA_STRATEGY.md) - Phase C 데이터 활용 전략
3. [FINETUNING_EXPERIMENT_PLAN.md](FINETUNING_EXPERIMENT_PLAN.md) - 파인튜닝 학습 로드맵과 실험 전략
4. [PHASE_D_EXIT_CRITERIA.md](PHASE_D_EXIT_CRITERIA.md) - Phase D 완료 조건과 Phase E 착수 gate
5. [TEST_CRITERIA.md](TEST_CRITERIA.md) - 테스트 기준, 평가 기준, 참고 레퍼런스
6. [AGENTS.md](../AGENTS.md) - 협업 운영 규칙과 PR 기준
7. [CONTRIBUTING.md](CONTRIBUTING.md) - 팀원 작업 가이드

작업 전에는 원격 상태를 먼저 확인합니다.

```bash
git fetch origin
git status
```

로컬 브랜치가 뒤처진 상태에서 코드 구조나 구현 여부를 단정하지 않습니다.

---

## 워크스페이스 구조

현재 기본 구조는 다음과 같습니다. Phase C 산출물인 데이터 전략, JSON schema, tiny dataset fixture, validation test는 이 구조 위에 추가되어 있습니다. Phase D에서는 baseline inference와 evaluation helper를 이 책임 경계 안에서 확장합니다.

```text
AegisLM/
├── AGENTS.md                         # 협업 운영 매뉴얼
├── CONTRIBUTING.md                   # docs/CONTRIBUTING.md 안내 링크
├── README.md                         # 프로젝트 정체성과 개발 로드맵
├── docs/
│   ├── README.md                     # 문서 인덱스와 문서 관리 규칙
│   ├── CONTRIBUTING.md               # 팀원 작업 가이드
│   ├── DATA_STRATEGY.md              # Phase C 데이터 활용 전략
│   ├── FINETUNING_EXPERIMENT_PLAN.md # 학습 로드맵과 실험 전략
│   └── TEST_CRITERIA.md              # 테스트 기준과 평가 레퍼런스
├── pyproject.toml
├── uv.lock
├── aegislm/
│   ├── prompts/                      # prompt templates
│   ├── datasets/                     # dataset formatting and validation
│   ├── evaluation/                   # JSON validity and safety checks
│   ├── inference/                    # base/adaptor inference helpers
│   ├── training/                     # TRL / Unsloth helper code
│   └── schemas.py                    # Phase C JSON output contract
├── scripts/                          # future command entrypoints
├── configs/                          # future experiment configs
├── tests/
│   └── fixtures/
└── experiments/                      # 로컬 실험 로그, 대형 artifact 저장 금지
```

`.venv/`, cache, raw dataset, model checkpoint, adapter artifact, private CTI, secrets는 커밋하지 않습니다.

---

## 개발 환경 설정

의존성은 `uv` 기준으로 관리합니다.

```bash
uv sync
```

현재 Phase D에서는 baseline inference와 evaluation 기준선 확인이 우선입니다. 코드가 추가되거나 문서 기준이 바뀐 뒤에는 가능한 범위에서 다음 명령을 사용합니다.

```bash
uv run pytest tests/
uv run ruff check .
uv run ruff format --check .
uv run mypy aegislm/ tests/
```

GPU, 대형 모델, 외부 dataset이 필요한 실험은 일반 테스트와 분리하고 experiment log에 기록합니다.

---

## 브랜치 전략

`main`은 항상 동작 가능한 기준 브랜치로 유지합니다. 모든 작업은 브랜치를 만든 뒤 PR로 병합합니다.

브랜치 이름:

- `docs/<topic>`
- `feat/<topic>`
- `fix/<topic>`
- `test/<topic>`
- `refactor/<topic>`
- `experiment/<topic>`

예시:

- `docs/phase-a-project-identity`
- `feat/phase-b-scaffold`
- `test/evaluation-json-contract`
- `experiment/tiny-sft-poc`

---

## 커밋 메시지

Conventional Commits 형식을 권장합니다.

```text
<type>: <summary>
```

사용 가능한 type:

- `feat`
- `fix`
- `docs`
- `test`
- `refactor`
- `chore`
- `experiment`

예시:

- `docs: align contributing guide with model development scope`
- `feat: add dataset validation scaffold`
- `test: add json output contract checks`
- `experiment: add tiny sft poc config`

---

## 작업 범위 규칙

현재 로드맵에서 우선하는 작업:

- Phase A 문서/저장소 정체성 정리 (완료)
- Phase B 최소 scaffold 생성 (완료)
- Phase C 데이터 전략, JSON schema, tiny dataset 준비 (완료)
- Phase D baseline inference와 evaluation 기준 준비 (현재)
- Phase E tiny SFT PoC
- Phase F dataset 확장과 adapter 개선
- Phase G 직접 모델/레이어 연구

이 저장소에서 직접 담당하지 않는 작업:

- Project NuriLab의 정적 분석 시스템 구현
- Python analyzer rule 관리
- 운영용 보고서 생성기 구현
- 사용자 CLI 제품화
- Project NuriLab의 전체 배포 정책 정의
- 실제 악성 샘플 저장 또는 실행

Owner 확인 후 진행해야 하는 작업:

- schema 변경
- dataset format 변경
- prompt contract 변경
- evaluation metric 변경
- raw dataset, checkpoint, adapter 저장 정책 변경
- 실제 악성 샘플 취급과 관련된 모든 작업
- 직접 model architecture 변경

---

## 테스트와 검증

문서 변경만 수행한 PR은 문서 검토로 충분합니다.

코드 변경 PR은 가능한 범위에서 아래 명령을 실행합니다.

```bash
uv run pytest tests/
uv run ruff check .
uv run ruff format --check .
uv run mypy aegislm/ tests/
```

변경 영역별 테스트 기준:

- schema 변경: JSON contract와 required field 테스트
- dataset 변경: record validation, split, unsafe sample exclusion 테스트
- prompt 변경: expected message shape 또는 formatting snapshot 테스트
- evaluation 변경: invalid JSON, missing field, hallucinated mapping, unsafe guidance 테스트
- training helper 변경: config parsing과 dry-run 가능한 단위 테스트
- inference helper 변경: mock model 또는 fixture output 기반 테스트

실제 GPU 학습, 대형 모델 로딩, 외부 dataset 다운로드는 PR 필수 테스트가 아닙니다. 해당 검증은 별도 experiment log에 command, package version, GPU, dataset path, 결과를 기록합니다.

---

## PR 제출 규칙

PR은 작게 유지합니다. 하나의 PR에는 하나의 목적만 담습니다.

PR 제목:

```text
[AegisLM] <summary>
```

PR 본문은 [PR_DESCRIPTION_TEMPLATE.md](PR_DESCRIPTION_TEMPLATE.md)를 기준으로 작성합니다. 최소한 다음을 포함합니다.

- 변경 목적
- 주요 변경 내용
- 검증 명령과 결과
- 제한사항 또는 후속 작업
- 관련 Linear 이슈와 GitHub PR/Issue

PR 생성 전 체크리스트:

- [ ] 최신 `main` 기준 브랜치에서 작업
- [ ] 브랜치명이 규칙을 따름
- [ ] PR 제목이 `[AegisLM] <summary>` 형식을 따름
- [ ] 코드 변경에 테스트 포함 또는 테스트 생략 사유 작성
- [ ] schema, dataset, prompt, evaluation 변경 시 문서 갱신
- [ ] raw dataset, checkpoint, adapter artifact, secrets, 민감 데이터 미포함
- [ ] 실험 결과 주장 시 command, package version, GPU, dataset path 기록

---

## 보안과 데이터 취급

다음은 커밋하지 않습니다.

- 실제 악성코드 샘플
- API key, token, password
- private CTI
- private customer data
- 민감한 내부 코드
- raw dataset
- model checkpoint
- adapter artifact
- 개인 실험 결과 중 민감 정보가 포함된 파일
- `.venv/`, cache, 로컬 설정 파일

학습 데이터는 방어적 분석 목적에 맞아야 합니다. 공격 실행 절차, 우회 로직, credential theft workflow, persistence instruction, exploit execution step을 학습 대상으로 만들지 않습니다.

실제 악성 파일을 다루는 단계에서는 격리된 분석 환경, 네트워크 통제, 샘플 저장 정책, 접근 권한 관리, Owner 승인이 선행되어야 합니다.

---

## 막혔을 때

모호하거나 막히면 임의로 확장하지 말고 GitHub Issue 또는 PR 코멘트에 남깁니다.

특히 다음 판단은 혼자 확정하지 않습니다.

- 모델이 최종 판단자처럼 동작하도록 학습할지 여부
- Project NuriLab의 분석 결과를 학습 데이터로 가져오는 방식
- 공개 CTI나 외부 API 데이터의 저장 방식
- adapter merge 여부
- 직접 model architecture 변경 착수 여부
