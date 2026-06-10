# Test Criteria

이 문서는 `AegisLM` Phase C부터 적용할 테스트 기준과 참고 레퍼런스를 기록합니다.

Phase C의 목표는 파인튜닝을 바로 시작하는 것이 아니라, 데이터 전략을 먼저 정리한 뒤 모델 출력 계약과 평가 기준을 고정하는 것입니다. 이후 dataset, prompt, inference, training, evaluation 코드는 이 기준을 따라야 합니다.

## 1. Phase C 목표

- 데이터 활용 전략을 기준으로 fine-tuning, evaluation, RAG/vector 데이터 흐름을 분리한다.
- 모델이 생성해야 하는 JSON output contract를 명확히 정의한다.
- tiny dataset의 record shape와 expected output 형식을 고정한다.
- 올바른 예시는 통과하고, 잘못된 예시는 실패하는 validation test를 만든다.
- 평가 기준을 감이 아니라 문서화된 규칙과 테스트로 판단한다.

## 2. 테스트 기준 초안

Phase C에서 우선 정의할 기준:

- 출력은 반드시 JSON으로 parse 가능해야 한다.
- 출력은 JSON Schema validation을 통과해야 한다.
- 필수 필드는 누락되면 실패한다.
- enum 값은 허용된 값만 사용한다.
- confidence, risk_level, severity 계열 값은 문서화된 범위만 사용한다.
- ATT&CK mapping은 근거가 없으면 빈 배열 또는 `unknown`으로 처리한다.
- 공격 실행 절차, 우회 로직, credential theft workflow, persistence instruction, exploit execution step을 포함하면 실패한다.
- 모델 출력은 최종 보안 판단이 아니라 설명, 요약, 매핑, 우선순위화를 위한 중간 산출물로 취급한다.

## 3. 권장 평가 항목

Phase D 이후 baseline/adaptor 비교에서 사용할 후보 지표:

- JSON parse success rate
- JSON Schema validation pass rate
- required field completeness
- invalid enum rate
- behavior explanation usefulness
- ATT&CK tactic / technique mapping quality
- hallucinated TTP rate
- severity consistency
- unsafe or overly actionable guidance rate

정량 지표만으로 충분하지 않은 항목은 human review note를 함께 기록합니다.

## 4. 레퍼런스

### 출력 구조와 JSON Schema

- JSON Schema Specification: https://json-schema.org/specification
- OpenAI Structured Outputs: https://openai.com/index/introducing-structured-outputs-in-the-api/

OpenAI Structured Outputs는 OpenAI API 사용을 전제로 채택하는 것이 아니라, LLM 출력이 schema를 만족해야 한다는 구조화 출력 평가 철학을 참고하기 위한 자료입니다.

### 모델 평가 지표

- Google ML Crash Course - Accuracy, Precision, Recall: https://developers.google.com/machine-learning/crash-course/classification/accuracy-precision-recall
- scikit-learn Metrics: https://scikit-learn.org/stable/api/sklearn.metrics.html
- Hugging Face Evaluate: https://huggingface.co/docs/evaluate/en/base_evaluator

악성/정상 또는 위험도 분류는 false positive와 false negative 비용이 다르므로 accuracy만으로 판단하지 않습니다. precision, recall, F1, class별 support를 함께 확인합니다.

### 보안 라벨과 분류 체계

- MITRE ATT&CK: https://attack.mitre.org/
- MITRE ATT&CK Data & Tools: https://attack.mitre.org/resources/attack-data-and-tools/
- FIRST CVSS v4.0 Specification: https://www.first.org/cvss/specification-document
- NIST NVD: https://www.nist.gov/itl/nvd

ATT&CK mapping은 장기적으로 tactic, technique_id, technique_name을 MITRE ATT&CK 기준과 호환되게 관리합니다. CVSS/NVD는 취약점 severity와 metadata를 다룰 때 참고합니다.

### LLM 보안 위험

- OWASP Top 10 for LLM Applications: https://owasp.org/www-project-top-10-for-large-language-model-applications
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework

LLM 특유의 prompt injection, insecure output handling, unsafe guidance 문제는 별도 실패 기준으로 관리합니다.

### 파인튜닝 데이터 포맷

- OpenAI Fine-tuning Data Format: https://help.openai.com/en/articles/6811186
- OpenAI gpt-oss Fine-tuning Cookbook: https://cookbook.openai.com/articles/gpt-oss/fine-tune-transfomers
- Hugging Face TRL SFTTrainer: https://huggingface.co/docs/trl/main/en/sft_trainer
- Hugging Face Dataset Cards: https://huggingface.co/docs/hub/datasets-cards

OpenAI API fine-tuning 문서는 API 사용 목적이 아니라 instruction/input/output 또는 chat-style 학습 샘플 구조를 참고하기 위한 자료입니다.

## 5. Phase C 종료 조건

- JSON output contract가 문서와 코드 양쪽에 존재한다.
- tiny dataset fixture가 schema를 통과한다.
- invalid JSON, missing field, invalid enum, unsafe guidance fixture가 실패한다.
- 테스트 명령으로 schema validation 결과를 확인할 수 있다.
- README와 docs 문서가 현재 Phase C 상태를 가리킨다.

## 6. Phase C 초기 구현 기준

초기 구현은 `jsonschema` 기반 검증을 사용한다.

- JSON output contract와 dataset record schema는 `aegislm/schemas.py`에 둔다.
- 검증 API는 `aegislm/evaluation/validation.py`에 둔다.
- 첫 tiny fixture는 `tests/fixtures/tiny_phase_c_records.jsonl`에 JSONL 형식으로 둔다.
- raw CVE, KEV, ATT&CK 데이터는 `data/` 아래에만 보관하고 Git에 커밋하지 않는다.
- fixture는 metadata-only 또는 synthetic record만 포함하며 executable payload를 포함하지 않는다.
- ATT&CK mapping 근거가 부족한 fixture는 `attack_mapping: []`와 `limitations`를 함께 둔다.
