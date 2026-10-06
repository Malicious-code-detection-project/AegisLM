# AegisLM Docs

이 디렉터리는 `AegisLM`의 세부 기준과 실험 문서를 관리합니다.

루트 [README.md](../README.md)는 프로젝트 정체성, 현재 Phase, 큰 로드맵, 주요 문서 링크만 유지합니다. 세부 기준, 실험 계획, 기여 절차, 테스트 기준은 이 디렉터리 아래 문서에 기록합니다.

## 문서 지도

선택형 개인 하네스의 진입점·역할·교체 기록은 [프로필 인덱스](../references/이정민/index.md)에 있습니다.

| 문서 | 역할 |
| --- | --- |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 팀원이 작업을 시작하고 PR을 제출하기 위한 실행 가이드 |
| [ARTIFACT_STORAGE_POLICY.md](ARTIFACT_STORAGE_POLICY.md) | fine-tuning adapter, checkpoint, model card, evaluation artifact 저장 정책 |
| [DATASET_CANDIDATES.md](DATASET_CANDIDATES.md) | Phase D/E 이후 공개 데이터셋 후보 registry와 안전성/용도 분류 |
| [DATA_STRATEGY.md](DATA_STRATEGY.md) | Phase C 데이터 활용 전략, 전처리, tokenization/chunking, split, RAG/vector 분리 기준 |
| [DATASET_ARTIFACT_INVENTORY.md](DATASET_ARTIFACT_INVENTORY.md) | 기존 데이터셋 83개 폴더의 목적·결과·계보와 학습 전 정리 조건 |
| [EVALUATION_PLAN.md](EVALUATION_PLAN.md) | Phase D/E 평가 계획, 점수화 기준, JSON/HTML 리포트 형식 |
| [EXPERIMENT_LOG_TEMPLATE.md](EXPERIMENT_LOG_TEMPLATE.md) | baseline/adapter 평가 결과를 같은 형식으로 기록하기 위한 템플릿 |
| [PHASE_D_EXIT_CRITERIA.md](PHASE_D_EXIT_CRITERIA.md) | Phase D 완료 조건과 Phase E tiny SFT PoC 착수 gate |
| [PHASE_E_TEAM_ONBOARDING.html](PHASE_E_TEAM_ONBOARDING.html) | Phase E 이슈 처리와 팀 교육 주제를 한 장으로 정리한 온보딩 인포그래픽 |
| [FINETUNING_EXPERIMENT_PLAN.md](FINETUNING_EXPERIMENT_PLAN.md) | 파인튜닝 학습 로드맵, 실험 전략, 데이터셋 계획, [v5 판단 학습 실행·Unsloth 복구 기록](FINETUNING_EXPERIMENT_PLAN.md#2026-10-02-v5-decision-only-execution), [공식 GPT-OSS 예제 확보 기록](FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-unsloth-official-gpt-oss-20b-reference), [기존 코드와 공식 마스킹 비교](FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-final-only-mask-vs-empty-analysis-code-review) |
| [GPT_OSS_SERVING_TRAINING_ERROR_ANALYSIS.md](GPT_OSS_SERVING_TRAINING_ERROR_ANALYSIS.md) | vLLM 서빙과 판단 SFT의 이론·조건 차이, 공식100step 원문 오류 분류, 확인된 사실과 가설·후속 대조 계획 |
| [PR_DESCRIPTION_TEMPLATE.md](PR_DESCRIPTION_TEMPLATE.md) | PR 본문 작성 템플릿과 체크리스트 |
| [QUALITY_GATES.md](QUALITY_GATES.md) | 코드 변경 PR의 pytest, ruff, mypy 검사 기준 |
| [TEST_CRITERIA.md](TEST_CRITERIA.md) | Phase C 테스트 기준, JSON schema 검증 기준, 평가 레퍼런스 |

## 문서 관리 규칙

최근 실험은 [SFTTrainer final-only 학습·native EOS 기록](FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-sfttrainer-final-only-mask-eos-return),
[최대 문맥 생성 비교](FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-context-window-max-131072-generation-experiment),
[원본 튜토리얼 학습·최대 생성 상한 비교](FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-unsloth-original-max-new-tokens-131072-training),
[공식 튜토리얼 원본 조건·생성64 실행 결과와 라벨 분석](FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-unsloth-official-tutorial-generation-64),
[공식 학습에 v5 데이터 연결·완료된 생성 길이 비교와 Harmony 파서 분석](FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-official-tutorial-v5-dataset-token-caps),
[max_steps만100으로 늘린 완료 결과·30step 비교](FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-official-tutorial-v5-max-steps-100)를 참고합니다.
해석과 학습·서빙·평가의 구분은 [GPT-OSS 오류 분석](GPT_OSS_SERVING_TRAINING_ERROR_ANALYSIS.md)에 기록합니다.

- README에는 프로젝트의 큰 방향과 현재 상태만 적는다.
- 세부 기준, 실험 계획, 기여 규칙, 테스트 기준은 `docs/` 아래 문서에 기록한다.
- 새 기준이 생기면 가장 가까운 기존 문서에 추가한다.
- 성격이 독립적인 기준이면 `docs/`에 새 문서를 만든다.
- 문서를 추가하거나 이동하면 `README.md`, `docs/README.md`, `AGENTS.md`의 링크와 작업 규칙을 함께 갱신한다.
- schema, dataset format, prompt contract, evaluation metric 변경은 관련 문서와 테스트를 함께 갱신한다.
