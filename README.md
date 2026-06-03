# AegisLM

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

초기 기준 모델은 `openai/gpt-oss-20b`입니다.

v0 단계에서는 악성코드 유사 스크립트 동작 설명, 취약점 맥락 요약, CTI 메타데이터 정리, ATT&CK 매핑, 위험도 우선순위화를 JSON 형식으로 생성하는 모델을 목표로 합니다.

모델은 최종 보안 판단자가 아닙니다. 판단 근거는 deterministic analyzer, rule signal, curated evidence에 두고, 모델은 설명, 요약, 매핑, 보고서 구조화를 담당합니다.

## 개발 로드맵

**Phase A: 문서/저장소 정체성 정리 (완료)**

    이 프로젝트는 Project Nurilab : 로컬 LLM 기반 악성코드 분석 자동화 시스템 개발 프로젝트에서 `로컬 LLM 파인 튜닝 또는 LLM 모델링` 부분을 담당하는 프로젝트입니다. `README.md`, `AGENTS.md`, `docs/CONTRIBUTING.md`의 방향성은 이 기준에 맞춰 정리했습니다.


**Phase B: 최소 코드 뼈대 생성 (완료, 최초 push 준비)**

    학습 코드를 바로 크게 만들기보다, 데이터, 평가, 학습, 추론의 책임 경계를 나누는 얇은 scaffold를 만듭니다. 이 단계의 목표는 전체 구조를 이해할 수 있는 최소 패키지와 디렉터리 구조를 만드는 것입니다. 실제 학습 방식, notebook/script/config 중심 선택, TRL/Unsloth 우선순위는 Phase B 이후에 결정합니다.

-> **Phase C: JSON schema + tiny dataset (진행 중)**

    모델이 생성해야 할 JSON output contract를 코드와 문서 양쪽에서 고정하고, 5-20개 수준의 작은 synthetic 또는 metadata-only 학습 예시를 준비합니다. 이 단계에서는 대형 데이터셋이나 실제 악성 샘플을 다루지 않습니다.

**Phase D: baseline inference + evaluation**

    파인튜닝 전에 `openai/gpt-oss-20b` 기본 모델의 출력을 먼저 확인하고, JSON parse success, required field completeness, hallucinated ATT&CK mapping, unsafe guidance 여부를 평가합니다. 학습 전 baseline이 있어야 이후 adapter가 실제로 좋아졌는지 판단할 수 있습니다.

**Phase E: tiny SFT PoC**

    작은 데이터셋으로 Unsloth QLoRA와 Hugging Face TRL LoRA / QLoRA 경로를 비교합니다. 목표는 큰 성능 향상이 아니라, 학습 루프, adapter 저장/로드, 평가 흐름을 끝까지 검증하는 것입니다.

**Phase F: dataset 확장 + adapter 개선**

    평가 기준이 안정된 뒤 NVD, CISA KEV, MITRE ATT&CK, 공개 CTI, Project NuriLab synthetic fixture 같은 안전한 데이터 소스를 확장합니다. adapter 품질은 JSON 유효성, 설명 품질, ATT&CK 매핑 정확도, 안전성 기준으로 개선합니다.

**Phase G: 직접 모델/레이어 연구**

    LoRA / QLoRA, dataset, evaluation이 충분히 안정된 뒤 직접 모델 구조 변경, custom layer, continued pretraining 같은 연구를 검토합니다. 이 단계는 장기 목표이며, v0에서는 architecture modification을 하지 않습니다.

## Project NuriLab과의 관계

이 프로젝트는 Project Nurilab : 로컬 LLM 기반 악성코드 분석 자동화 시스템 개발 프로젝트에서 `로컬 LLM 파인 튜닝 또는 LLM 모델링` 부분을 담당하는 프로젝트입니다.

Project NuriLab은 나중에 AegisLM에서 만든 모델, LoRA adapter, 평가 결과, JSON output contract를 가져다 쓸 수 있습니다. 반대로 AegisLM은 Project NuriLab의 분석 결과나 synthetic fixture를 학습 데이터 후보로 활용할 수 있습니다.

두 프로젝트는 연결될 수 있지만, 책임은 분리합니다.

## 범위 밖

- 정적 분석 pipeline 구현
- Python analyzer rule 관리
- HTML 운영 보고서 생성기 구현
- 사용자 CLI 제품화
- Project NuriLab의 전체 배포 정책 정의
- 실제 악성 샘플 저장 또는 실행
- secrets, private CTI, private customer data 저장

## 문서

- `AGENTS.md` - 협업 운영 규칙
- `CONTRIBUTING.md` - 기여 절차 안내
- `docs/README.md` - 세부 문서 인덱스와 문서 관리 규칙
- `docs/FINETUNING_EXPERIMENT_PLAN.md` - 파인튜닝 실험 계획
- `docs/TEST_CRITERIA.md` - Phase C 테스트 기준과 평가 레퍼런스

README에는 프로젝트의 큰 방향과 현재 상태만 유지합니다. 세부 기준, 실험 계획, 기여 규칙, 테스트 기준은 `docs/` 아래 문서에 기록합니다.
