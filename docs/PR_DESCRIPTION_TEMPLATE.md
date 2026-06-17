# PR Description Template

이 문서는 `AegisLM` PR 본문을 일관되게 작성하기 위한 재사용 템플릿입니다.

PR에는 변경 목적, 구현 범위, 제외 범위, 검증 결과, Linear 이슈 연결, 남은 후속 작업을 명확히 기록합니다. 한국어와 영어를 같이 작성해야 하는 경우 같은 섹션 안에서 병기합니다.

## 사용 방법

1. 아래 템플릿을 PR 본문에 붙여 넣는다.
2. `<...>` placeholder를 실제 값으로 바꾼다.
3. 해당하지 않는 항목은 삭제하지 말고 `N/A` 또는 `해당 없음`으로 명시한다.
4. schema, dataset format, prompt contract, evaluation metric, artifact storage policy를 바꾸는 PR은 관련 문서와 테스트 갱신 여부를 반드시 적는다.

## Template

```markdown
## 무엇을 / 왜 / What and Why

Closes <THE-XX>
Relates to <THE-YY, optional>

<이 PR이 해결하는 문제와 의도를 한국어로 설명합니다.>

<Describe the intent and problem this PR solves in English if needed.>

현재 Phase: <Phase C/D/E...>
작업 범위: <docs/schema/dataset/evaluation/inference/training/etc.>

## 구현 / Implementation

- <주요 변경 1>
- <주요 변경 2>
- <주요 변경 3>

핵심 파일:

- `<path/to/file>` - <역할>
- `<path/to/file>` - <역할>

## 범위 제외 / Out of Scope

- <이번 PR에서 의도적으로 하지 않은 작업>
- <후속 Linear 이슈로 남길 작업>

## 계약 / Interfaces and Contracts

- Public API 변경: <있음/없음>
- Schema 변경: <있음/없음>
- Dataset format 변경: <있음/없음>
- Prompt contract 변경: <있음/없음>
- Evaluation metric 변경: <있음/없음>
- Artifact storage policy 변경: <있음/없음>

변경이 있는 경우 관련 문서와 테스트:

- 문서: `<docs/...>`
- 테스트: `<tests/...>`

## AC 충족 / Acceptance Criteria

- [ ] <Linear 이슈의 완료 조건 1>
- [ ] <Linear 이슈의 완료 조건 2>
- [ ] <Linear 이슈의 완료 조건 3>

## 구조 정합 / Structure Alignment

- 책임 경계: `<aegislm/...>`에 배치한 이유를 적습니다.
- 관련 SSOT: `<README.md>`, `<docs/...>`, `<AGENTS.md>` 중 어떤 문서와 맞췄는지 적습니다.
- 불일치 또는 후속 정리 필요 사항: <없음/내용>

## 체크리스트 / Checklist

- [ ] `git fetch origin` 후 최신 기준 확인
- [ ] 브랜치명이 `AGENTS.md` 네이밍 표준을 따름
- [ ] PR 제목이 `[AegisLM] <summary>` 형식을 따름
- [ ] raw dataset, checkpoint, adapter artifact, secrets, 민감 데이터 미포함
- [ ] 모델, adapter, checkpoint, raw dataset은 Git 밖에 유지
- [ ] schema/dataset/prompt/evaluation 변경 시 문서와 테스트 함께 갱신
- [ ] 실험 결과 주장 시 command, package version, GPU, dataset path 기록

## 검증 / Validation

- `uv run pytest tests/`
  - <결과>
- `uv run ruff check .`
  - <결과>
- `uv run ruff format --check .`
  - <결과>
- `uv run mypy aegislm/ tests/`
  - <결과>

추가 검증이 있는 경우:

- `<command>`
  - <결과>

실행하지 않은 검증:

- <명령> - <실행하지 않은 이유>

## 참고 / References

- Linear: <THE-XX>
- Phase/Milestone: <Phase ...>
- Related docs: `<docs/...>`
- Related PRs/issues: <links>
```

## 작성 기준

- PR 본문은 리뷰어가 변경 목적과 검증 상태를 빠르게 판단할 수 있게 작성한다.
- 큰 설명보다 실제 변경 파일, 계약 변경 여부, 검증 명령, 후속 작업을 우선한다.
- LLM/보안 분석 관련 실험 결과를 주장할 때는 재현 가능한 command와 환경 정보를 함께 적는다.
- 실제 악성 샘플, secrets, private CTI, raw dataset, model artifact가 포함되지 않았음을 확인한다.
