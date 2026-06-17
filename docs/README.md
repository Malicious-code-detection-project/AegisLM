# AegisLM Docs

이 디렉터리는 `AegisLM`의 세부 기준과 실험 문서를 관리합니다.

루트 [README.md](../README.md)는 프로젝트 정체성, 현재 Phase, 큰 로드맵, 주요 문서 링크만 유지합니다. 세부 기준, 실험 계획, 기여 절차, 테스트 기준은 이 디렉터리 아래 문서에 기록합니다.

## 문서 지도

| 문서 | 역할 |
| --- | --- |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 팀원이 작업을 시작하고 PR을 제출하기 위한 실행 가이드 |
| [ARTIFACT_STORAGE_POLICY.md](ARTIFACT_STORAGE_POLICY.md) | fine-tuning adapter, checkpoint, model card, evaluation artifact 저장 정책 |
| [DATASET_CANDIDATES.md](DATASET_CANDIDATES.md) | Phase D/E 이후 공개 데이터셋 후보 registry와 안전성/용도 분류 |
| [DATA_STRATEGY.md](DATA_STRATEGY.md) | Phase C 데이터 활용 전략, 전처리, tokenization/chunking, split, RAG/vector 분리 기준 |
| [EVALUATION_PLAN.md](EVALUATION_PLAN.md) | Phase D/E 평가 계획, 점수화 기준, JSON/HTML 리포트 형식 |
| [FINETUNING_EXPERIMENT_PLAN.md](FINETUNING_EXPERIMENT_PLAN.md) | 파인튜닝 학습 로드맵, 실험 전략, 데이터셋 계획 |
| [PR_DESCRIPTION_TEMPLATE.md](PR_DESCRIPTION_TEMPLATE.md) | PR 본문 작성 템플릿과 체크리스트 |
| [QUALITY_GATES.md](QUALITY_GATES.md) | 코드 변경 PR의 pytest, ruff, mypy 검사 기준 |
| [TEST_CRITERIA.md](TEST_CRITERIA.md) | Phase C 테스트 기준, JSON schema 검증 기준, 평가 레퍼런스 |

## 문서 관리 규칙

- README에는 프로젝트의 큰 방향과 현재 상태만 적는다.
- 세부 기준, 실험 계획, 기여 규칙, 테스트 기준은 `docs/` 아래 문서에 기록한다.
- 새 기준이 생기면 가장 가까운 기존 문서에 추가한다.
- 성격이 독립적인 기준이면 `docs/`에 새 문서를 만든다.
- 문서를 추가하거나 이동하면 `README.md`, `docs/README.md`, `AGENTS.md`의 링크와 작업 규칙을 함께 갱신한다.
- schema, dataset format, prompt contract, evaluation metric 변경은 관련 문서와 테스트를 함께 갱신한다.
