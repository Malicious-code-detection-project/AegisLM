# AegisLM

2026-09-28 C/C++ 원천 데이터 재구성 결과는
`data/processed/cc-source-candidates-20260928-v5`에 보관합니다. 여섯 원천의
1,012,598개 후보를 공통 형식으로 정리하고, 그중 판단 라벨이 있는
10,000/1,000/500건을 분리했습니다. 최종 파일 기준 코드·CVE·커밋·함수
그룹 및 설정된 유사도 기준의 분할 간 중복 검사를 통과했습니다.
이는 원천 라벨 기반 후보이며, CWE 판단과 근거 줄 검수는 아직 완료되지
않았습니다. 세부 계약과 재현 방법은 [데이터 전략](docs/DATA_STRATEGY.md)의
C/C++ raw-source reconstruction 절을 참고합니다.
2026-09-29 결정에 따라 이력을 보존했고, 2026-10-02 재생성 검증 후
중간 v1–v4 정리를 완료했습니다. 정규화 풀은 별도 캐시로 이관했으며
최종 v5의 파일과 10,000/1,000/500 구성은 그대로 유지됩니다.
2026-10-03 RTX A6000 1장에서 v5 판단 전용 base development100 평가와
Unsloth 100-step 본 학습을 완료했습니다. 평균 학습 loss는 0.209771,
마지막 step loss는 0.028211이며 W&B에서 100개 step 기록과 종료 상태를
확인했습니다. 최종 adapter는 새 프로세스에서 저장값과 일치했습니다.
현재 실행 경로는 `cc-decision-20261002-v7`입니다. base는 128-token 예산에서
100건 모두 final JSON을 생성하지 못했습니다. test500 품질 비교는 아직
실행하지 않았으며, 이전 batch2 수치 비교 실패도 진단 이력으로 남아 있습니다.
2026-10-03에는 `max-new-tokens-65536` 생성 한도 비교 실험도 완료했습니다.
동일 validation2건에서 base는 2,048/65,536 한도로 JSON1건이 회복됐지만
adapter는 모든 한도에서 JSON0건이었고 message/channel token 반복이 나타났습니다.
전체 문맥 한도131,072와 생성 상한65,536을 구분해 기록했으며, 실험표·가설·
중간 실패·재현 자료는 아래 실행 안내의 `max-new-tokens-65536` 절에 보존합니다.
2026-10-04에는 공식 Unsloth GPT-OSS-20B 예제를 기준으로 재시작하기로 했습니다.
공식 노트북·Python 예제·출처와 hash를 확보하고 기존 경로와 차이를 기록했습니다.
세부 내용은 [공식 예제 확보 기록](docs/FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-unsloth-official-gpt-oss-20b-reference)을 참고합니다.
기존 학습 코드와의 CPU 비교에서는32건의 입력 마스킹·EOS는 정상이었고,
공식 final-only mask와 달리 빈 analysis 및 final header9토큰도 학습했습니다.
이 차이의 인과는 미확정이며, [코드 비교 기록](docs/FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-final-only-mask-vs-empty-analysis-code-review)에 확인된 평가 설정 문제와 함께 남겼습니다.
공식 예제의 SFTTrainer/final-only 경로와 native EOS 비교를 위한 새 recipe는
[실험 실행 기록](docs/FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-sfttrainer-final-only-mask-eos-return)에 기록합니다.
GPU 사전 검사 통과 후100-step 학습과 최종 어댑터 저장을 완료했습니다.
평균 학습 loss는0.119957, 최종 검증 loss는4.981067로 차이가 큽니다.
저장한 어댑터를 새 프로세스에서 불러온 동일 validation2건 비교에서
bare-assistant는 둘 다 analysis 반복 후 시간 제한에 도달했습니다.
gold-free final-prefill은 둘 다 JSON/schema 및 원천 라벨이 일치했고,
7/9토큰 뒤 native return으로 종료했습니다. 기존8행에 새2행을 추가했습니다.
이는 시작 형식의 영향에 대한 진단이며, 표본2건으로 품질 합격을 주장하지 않습니다.
같은 날 [context-window-max-131072 실험](docs/FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-context-window-max-131072-generation-experiment)도 완료했습니다.
입력을 뺀 최대 생성 상한130,770–130,837을 적용했지만 adapter/bare는
같은 출력 접두부를 반복하다300초 제한에 걸렸고, final-prefill은 이전과 같은
7/9토큰으로 종료했습니다. 실제 최대 길이까지 생성한 실험은 아닙니다.
이후에는 [원본 튜토리얼 학습·최대 생성 상한 실험](docs/FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-unsloth-original-max-new-tokens-131072-training)을 분리했습니다.
원본 Multilingual-Thinking 데이터와1,024-token/30-step 설정으로 새 학습을
완료했고, 평균 loss는1.024378입니다. 로컬 compiler 호환 오류의 실패 이력을
보존하고 Unsloth의 compiler-off 경로를 사용했습니다. 동일 runtime의
base/adapter8조건 비교도 완료했습니다. 최대 생성 예산130,950의4조건은
모두600초 제한에 도달했고 adapter medium만 부분 final이 있었으며,
native EOS는0/4입니다. 실제 생성량은약3,000으로 최대 길이를 소진한 검증은
아닙니다. 이 수학 시연을 C/C++ 판단 품질 비교와 구분해 기록합니다.
이전 실험의 600초 제한은 사용자가 승인하지 않은 조건 변경이었으므로,
생성 상한만 바꾼 공식 재현 결과로 간주하지 않습니다.
[공식 튜토리얼 그대로의 새 실행](docs/FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-unsloth-official-tutorial-generation-64)은
새 독립 환경에서 학습1,024토큰·30스텝, 원본 생성5회·64토큰을 완료했습니다.
compiler 우회와 외부 시간 제한 없이 평균 train loss1.003214를 기록하고
adapter를 저장했습니다. 생성5회 모두64토큰 예산을 소진해 analysis 중간에서
끝났으며 완성된 final은 없습니다. 실제 원본 mask는 final만 직접 학습하고
analysis는 제외하므로, 이 결과를 French reasoning 적응 성공으로 보지 않습니다.
validation과 W&B는 원본대로 비활성입니다. 결과표·원문·라벨 검사를 보고서에 기록했습니다.
이어서 [공식 학습에 v5 데이터를 연결하는 실험](docs/FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-official-tutorial-v5-dataset-token-caps)을 완료했습니다.
원본1,024토큰·30스텝의 평균 train loss는0.230625입니다. 실제 유효 train은
8,525건이며, 동일 validation2건에 공식 기본 생성과5개 토큰 상한을 적용한
base/adapter20호출을 마쳤습니다. adapter는2,048/65,536/남은 최대 문맥 조건에서
두 건 모두 유효 JSON과 원천 라벨 일치를 기록했습니다. 짧은 예산의 실패와
정상 Harmony final을 누락한 평가 파서3건을 구분해 결과표에 남겼습니다.
이는2건 진단이며 전체 test500 품질 검증은 아닙니다.
같은 데이터·독립 환경·생성 조건에서 [max_steps만100으로 늘리는 실험](docs/FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-official-tutorial-v5-max-steps-100)도 완료했습니다.
평균 train loss는0.130558로 낮아졌지만 생성20호출에서 일관된 품질 개선은
확인되지 않았습니다. adapter512는 라벨 일치2/2,2048은0/2,65536·최대 문맥은
각1/2였으며 오분류·tool request·추가 필드 실패를 구분했습니다.
같은 초기 가중치·학습 설정·데이터·생성 코드를 대조했고30step 비교표를 보존했습니다.
2026-10-05 [vLLM 서빙과 판단 학습의 차이·오류 분석](docs/GPT_OSS_SERVING_TRAINING_ERROR_ANALYSIS.md)을 작성했습니다.
최근100step 학습은 완료됐으며, 생성 예산 소진·tool handoff·출력 계약·판단 오류와
평가 파서의 누락을 구분했습니다. 현재 학습 target은 판단 한 필드이고 이유·추천
사항의 학습·품질 평가와는 다릅니다. 과거 vLLM 성공 사례와의 동일 조건 비교는 미검증입니다.
2026-10-06 코드 감사에서 생성 상한을 바꿀 때 모델을 다시 로드하지 않았음을 확인했습니다.
모델×상한마다 새 프로세스로 평가하도록 수정하고 입력 준비·CPU 검증을 마쳤습니다.
이후 v2 GPU 평가에서 조건별 프로세스 종료·재로딩을 실측했습니다.
adapter의128/512/2048조건 각100건과65536조건2건을 완료한 뒤,
같은825token 입력에서 CUDA OOM으로 중단됐습니다. 새302건은 기존v1과
별도로 보존했으며, base와 나머지 상한은 미실행입니다. 초기화 요구는 실행된
4조건에서 확인했지만 메모리 부족은 해결되지 않았습니다.
[조건별 초기화 감사](docs/GPT_OSS_SERVING_TRAINING_ERROR_ANALYSIS.md#1113-2026-10-06-생성-상한-변경-시-모델-재로딩-여부-감사와-수정)에 근거와 제한을 기록합니다.
현재 명령과 결과는
[v5 판단 학습 실행 안내](docs/FINETUNING_EXPERIMENT_PLAN.md#2026-10-02-v5-decision-only-execution)에 기록합니다.
기존 83개 데이터셋 폴더의 목적·결과·계보와 보존 조건은
[폴더 이력 및 정리 기록](docs/DATASET_ARTIFACT_INVENTORY.md)에 정리했습니다.

`AegisLM`은 Project NuriLab과 연계할 수 있는 별도 LLM 모델 개발 프로젝트입니다.

이 저장소는 보안 분석 시스템 자체를 구현하기보다, 보안 분석에 특화된 로컬 LLM을 학습, 평가, 개선하는 데 집중합니다. Project NuriLab이 분석 파이프라인과 운영 시스템을 담당한다면, AegisLM은 그 시스템에 연결될 수 있는 모델, 어댑터, 데이터셋, 평가 방법을 준비합니다.

## 왜 별도 프로젝트인가

LLM 모델 개발은 분석 파이프라인 구현과 다른 속도로 움직입니다. 학습 데이터, GPU 환경, 모델 체크포인트, 평가 기준, 안전 정책은 별도의 실험 관리가 필요합니다.

따라서 이 프로젝트는 Project NuriLab의 코드 구조나 릴리스 일정에 종속되지 않고, 모델 개발 관점에서 독립적으로 실험을 축적합니다.

## 핵심 목표

- 로컬 LLM 파인튜닝 실험
- LoRA / QLoRA 기반 학습 경로 검증
- 보안 분석 특화 데이터셋 구성과 정제
- JSON 구조화 출력 학습
- 모델 출력 품질 평가 harness 준비
- 장기적으로 보안 분석 특화 LLM 모델 직접 구축

## 현재 초점

현재 저장소 단계는 **Phase E: source-v2 tiny SFT PoC**입니다.

Phase E에서 tiny Unsloth QLoRA 학습과 adapter 저장/로드 가능성을 확인했습니다.
현재는 data/processed/phase-f-source-v5-r1의 C/C++ 함수 단위 데이터로
openai/gpt-oss-20b base와 source-v2 QLoRA adapter를 동일 조건에서 비교하는
재현 가능한 학습·평가 경로를 구축합니다.

2026-09-10 기준 1,000-record Unsloth QLoRA canary는 학습, expert adapter
저장, 재로딩까지 성공했지만 held-out JSON/schema/grounding gate가 0/40으로
실패했습니다. 따라서 full 10,000-record 학습과 base/adapter 본 비교는 아직
실행하지 않았으며, 실패 산출물은 Git 제외 경로에 보존합니다.

보존 산출물 재분석 결과 31/40은 JSON 파싱 실패였고, parse된 9건도 모두
contract를 위반했습니다. batch 1/8 재현에서는 동일한 8건의 JSON parse가
2/8 대 0/8로 달라져 batched generation 상호작용이 확인됐으며, checkpoint
25/100/final의 parse가 8/8, 6/8, 2/8로 악화돼 과적합 또는 control-token
degeneration도 별도 원인으로 확인했습니다. 수정 경로는 명시적인 low
reasoning/EOS/padding, batch-1 gate, 25-step checkpoint와 직접 PEFT injection
control을 사용합니다.

2026-09-11 복구 카나리도 같은 40건 gate에서 모두 0/40으로 실패했습니다.
`unsloth_v2`는 JSON parse 16/40·EOS 24/40, 직접 PEFT control은 parse
5/40·EOS 9/40이었고 두 adapter 모두 576개 LoRA tensor를 정상 저장·재로딩한
상태였습니다. 각 checkpoint-25의 고정 8건도 strict valid 0/8이어서 full
학습은 계속 차단합니다. 다음 데이터 분포 ablation을 위한 CWE/assessment
이중 층화 selector와 독립 config는 준비했지만, 현재 진단은 CWE 불균형보다
Harmony 제어 토큰 반복과 조기 semantic contract 실패를 우선 원인으로
지목하므로 해당 장시간 학습은 아직 실행하지 않았습니다.

학습 stage와 gate evidence는 append-only로 취급합니다. 완료되었거나 일부
산출물이 남은 stage를 같은 명령으로 다시 실행해 덮어쓰지 않으며, resume은
동일 config의 미완료 reservation과 그 checkpoint 바로 아래에서만 허용합니다.
full stage 승격 시에는 보고서의 집계값만 신뢰하지 않고 보존 prediction을
다시 채점해 record 집합, adapter 전체 artifact digest와 함께 검증합니다.

학습·평가·비교 결과는 선택적으로 Weights & Biases에 기록할 수 있습니다.
연동은 `--wandb`를 명시한 실행에만 활성화됩니다. 보존된 실패 canary의
source-free 집계와 125-step curve는 2026-09-11 W&B에 historical-import로
기록됐고, 복구 카나리는 W&B run `mdotwa7l`과 `4a0wl8na`에 실패 결과로
보존됐습니다. 자격 증명과 상세 실행법은
`docs/FINETUNING_EXPERIMENT_PLAN.md`를 따릅니다.

2026-09-27에는 사용자가 AegisLM-B200의 Qwen3 실험과 비교할 목적으로
10,000/1,000/500 데이터 구성을 유지한 탐색적 본 학습을 승인했습니다.
기존 canary 실패는 유지하며, 별도 설정과 명시적 실행 사유를 통해 본 학습을
시작했습니다. 학습 완료나 품질 개선은 아직 확인하지 않았습니다. 실행 조건과
검증 범위는 `docs/FINETUNING_EXPERIMENT_PLAN.md`의 전체 데이터 비교 실험
기록을 따릅니다.

초기 기준 모델은 `openai/gpt-oss-20b`입니다.

사용자가 직접 실행할 새 Unsloth recipe `unsloth_fresh_v1`과
`smoke → canary → full` 진입점을 추가했습니다. 이 recipe의 학습·GPU 검증은
진단 로그 추가 전 스모크 학습·adapter 재로딩은 완료했으나 출력 품질 gate는 통과하지 못했습니다.
입력·출력 진단 로그를 추가한 현재 변경은 정적 검사까지만 수행했습니다.
실행 명령과 제한사항은
[`새 Unsloth 수동 실행 안내`](docs/FINETUNING_EXPERIMENT_PLAN.md#15-fresh-unsloth-manual-run)를 참고합니다.

v0 단계에서는 악성코드 유사 스크립트 동작 설명, 취약점 맥락 요약, CTI 메타데이터 정리, ATT&CK 매핑, 위험도 우선순위화를 JSON 형식으로 생성하는 모델을 목표로 합니다.

모델은 최종 보안 판단자가 아닙니다. 판단 근거는 deterministic analyzer, rule signal, curated evidence에 두고, 모델은 설명, 요약, 매핑, 보고서 구조화를 담당합니다.

## 개발 로드맵

**Phase A: 문서/저장소 정체성 정리 (완료)**

이 프로젝트는 Project Nurilab : 로컬 LLM 기반 악성코드 분석 자동화 시스템 개발 프로젝트에서 `로컬 LLM 파인 튜닝 또는 LLM 모델링` 부분을 담당하는 프로젝트입니다. `README.md`, `AGENTS.md`, `docs/CONTRIBUTING.md`의 방향성은 이 기준에 맞춰 정리했습니다.


**Phase B: 최소 코드 뼈대 생성 (완료, 최초 push 준비)**

학습 코드를 바로 크게 만들기보다, 데이터, 평가, 학습, 추론의 책임 경계를 나누는 얇은 scaffold를 만듭니다. 이 단계의 목표는 전체 구조를 이해할 수 있는 최소 패키지와 디렉터리 구조를 만드는 것입니다. 실제 학습 방식, notebook/script/config 중심 선택, TRL/Unsloth 우선순위는 Phase B 이후에 결정합니다.

**Phase C: 데이터 전략 + JSON schema + tiny dataset (완료)**

데이터 활용 전략을 먼저 정리한 뒤 모델이 생성해야 할 JSON output contract를 코드와 문서 양쪽에서 고정하고, 5-20개 수준의 작은 synthetic 또는 metadata-only 학습 예시를 준비합니다. 이 단계에서는 대형 데이터셋, 실제 악성 샘플, GPU 학습, RAG embedding index 생성을 다루지 않습니다.

**Phase D: baseline inference + evaluation (완료)**

파인튜닝 전에 `openai/gpt-oss-20b` 기본 모델의 출력과 평가 기준선을 확인하는 구조를 마련했습니다. baseline inference, JSON parse success, required field completeness, hallucinated ATT&CK mapping, unsafe guidance 여부를 adapter 개선 전 비교 기준으로 사용합니다.


-> **Phase E: tiny SFT PoC (진행 중)**

작은 데이터셋으로 Unsloth QLoRA와 Hugging Face TRL LoRA / QLoRA 경로를 비교합니다. 목표는 큰 성능 향상이 아니라, 학습 루프, adapter 저장/로드, held-out evaluation 비교 흐름을 끝까지 검증하는 것입니다.

**Phase F: dataset 확장 + adapter 개선**

평가 기준이 안정된 뒤 NVD, CISA KEV, MITRE ATT&CK, 공개 CTI, Project NuriLab synthetic fixture 같은 안전한 데이터 소스를 확장합니다. adapter 품질은 JSON 유효성, 설명 품질, ATT&CK 매핑 정확도, 안전성 기준으로 개선합니다.

**Phase G: 직접 모델/레이어 연구**

LoRA / QLoRA, dataset, evaluation이 충분히 안정된 뒤 직접 모델 구조 변경, custom layer, continued pretraining 같은 연구를 검토합니다. 이 단계는 장기 목표이며, v0에서는 architecture modification을 하지 않습니다.

## Project NuriLab과의 관계

이 프로젝트는 Project Nurilab : 로컬 LLM 기반 악성코드 분석 자동화 시스템 개발 프로젝트에서 `로컬 LLM 파인 튜닝 또는 LLM 모델링` 부분을 담당하는 프로젝트입니다.

Project NuriLab은 AegisLM의 자체 검증이 끝난 뒤 base model 식별자와
fine-tuned adapter, 평가 결과, JSON output contract를 전달받을 수 있습니다.
성능 결과가 향상·동등·저하 중 무엇이든 유효하게 로드되는 산출물과 결과를
보존합니다.

Project NuriLab 저장소 수정, 런타임 연결, 통합 검증은 Project NuriLab의
책임이며 현재 AegisLM 실험 범위에 포함하지 않습니다.

## 범위 밖

- 정적 분석 pipeline 구현
- Python analyzer rule 관리
- HTML 운영 보고서 생성기 구현
- 사용자 CLI 제품화
- Project NuriLab의 전체 배포 정책 정의
- Project NuriLab 연동 코드, 설정, CLI, 통합 테스트 구현
- 실제 악성 샘플 저장 또는 실행
- secrets, private CTI, private customer data 저장

## 문서

선택형 개인 하네스는 [v4 진입점](references/이정민/index.md)에서 확인합니다.

- `AGENTS.md` - 협업 운영 규칙
- `CONTRIBUTING.md` - 기여 절차 안내
- `docs/README.md` - 세부 문서 인덱스와 문서 관리 규칙
- `docs/ARTIFACT_STORAGE_POLICY.md` - fine-tuning 산출물 저장 정책
- `docs/DATASET_CANDIDATES.md` - 공개 데이터셋 후보 registry와 안전성/용도 분류
- `docs/DATA_STRATEGY.md` - Phase C 데이터 활용 전략
- `docs/EVALUATION_PLAN.md` - Phase D/E 평가 계획과 결과 리포트 기준
- `docs/EXPERIMENT_LOG_TEMPLATE.md` - baseline/adapter 평가 결과 기록 템플릿
- `docs/PHASE_D_EXIT_CRITERIA.md` - Phase D 완료 조건과 Phase E 착수 gate
- `docs/PHASE_E_TEAM_ONBOARDING.html` - Phase E 이슈 처리와 팀 교육 주제 인포그래픽
- `docs/FINETUNING_EXPERIMENT_PLAN.md` - 파인튜닝 실험 계획
- [B200 재현 레시피](docs/B200_REPRODUCTION_RECIPE.md) - 동결 데이터 이관, 100-step 재학습, base·adapter의 동일 100건 평가
- `docs/PR_DESCRIPTION_TEMPLATE.md` - PR 본문 작성 템플릿
- `docs/QUALITY_GATES.md` - 코드 변경 PR 검사 기준
- `docs/TEST_CRITERIA.md` - Phase C 테스트 기준과 평가 레퍼런스

README에는 프로젝트의 큰 방향과 현재 상태만 유지합니다. 세부 기준, 실험 계획, 기여 규칙, 테스트 기준은 `docs/` 아래 문서에 기록합니다.

2026-09-28에는 B200의 성공 기준인 Q1R10 decision + Q1R11 evidence를
GPT-OSS에서 재현하는 `source_two_stage_v1` 경로를 추가했습니다. 동결된
판단·근거 데이터와 동일 평가 계약을 사용하며, 각각 base에서 100-step을
학습합니다. 준비/GPU 검증 → base dev100 → decision → evidence → 최종 평가를
순서대로 실행하고, 실패 시 다음 단계로 진행하지 않습니다. W&B 기록 확인을
학습 시작 조건으로 사용합니다. 실행 방법과 비교 조건은
`docs/FINETUNING_EXPERIMENT_PLAN.md`의 2026-09-28 항목을 따릅니다.
학습 완료와 품질 통과는 별도 실행 결과로 확인해야 합니다.

이 경로의 실제 준비 검증에서는 학습·검증 21,971건의 토큰 검사를
통과했지만, B200의 `fresh-blind-500` 중 498건이 현재 train/validation과
동일한 코드를 포함함을 확인했습니다. 준비 단계에서 차단했으며 GPU 학습과
W&B 학습 run은 시작하지 않았습니다. 원본은 보존하고, 실제 학습·검증 코드와
겹치지 않는 평가 세트를 먼저 확보해야 합니다. 상세 근거는 학습 계획 문서의
`Actual preparation result: blocked by benchmark overlap` 항목에 기록했습니다.
