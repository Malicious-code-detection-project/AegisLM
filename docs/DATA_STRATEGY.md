# Data Strategy

이 문서는 `AegisLM` Phase C의 데이터 활용 전략을 정의합니다.

Phase C는 구현을 바로 시작하는 단계가 아닙니다. 이 단계의 핵심은 어떤 데이터를 어떤 목적으로 사용할지, 어떤 전처리와 안전 기준을 적용할지, fine-tuning/evaluation/RAG 데이터를 어떻게 분리할지 먼저 결정하는 것입니다.

## 1. Goal

Phase C의 목표는 데이터 전략을 고정한 뒤 JSON schema, tiny dataset, validation test로 넘어가는 것입니다.

이 문서는 다음 질문에 답합니다.

- 어떤 데이터 소스를 사용할 수 있는가?
- 각 데이터는 fine-tuning, evaluation, RAG/vector, prompt example 중 어디에 쓰는가?
- 학습 샘플 하나의 단위는 무엇인가?
- 어떤 필드를 남기고 어떤 필드를 제거하는가?
- 긴 문서, 긴 분석 결과, 긴 코드/로그는 어떻게 chunking하는가?
- tokenization과 vectorization은 어떻게 구분하는가?
- train/validation/test split은 어떻게 나누는가?
- 어떤 데이터는 Git에 저장할 수 있고, 어떤 데이터는 저장하면 안 되는가?

## 2. Core Decision

AegisLM의 Phase C는 데이터로 시작해서 데이터로 끝납니다.

따라서 Phase C의 작업 순서는 다음을 따른다.

```text
data source inventory
-> data safety and exclusion policy
-> sample unit and record shape
-> preprocessing and normalization policy
-> tokenization, token budget, and chunking policy
-> fine-tuning / evaluation / RAG data flow separation
-> split and contamination policy
-> tiny dataset acceptance criteria
-> JSON output contract
-> validation test
```

JSON schema와 tiny dataset은 데이터 전략의 출발점이 아니라 결과물입니다.

## 3. Data Flow Separation

AegisLM은 데이터를 세 가지 경로로 나눠 관리합니다.

| Data flow | Purpose | Output |
| --- | --- | --- |
| Fine-tuning data | 모델이 어떤 형식과 기준으로 답해야 하는지 학습 | supervised examples, chat/instruction records |
| Evaluation data | 모델 출력 품질을 측정 | held-out fixtures, expected labels, review notes |
| RAG/vector data | 모델이 참고할 외부 근거를 검색 | chunks, embeddings, retrieval metadata |

세 경로는 같은 원천 데이터를 참고할 수 있지만, 저장 위치와 사용 목적은 분리합니다.

중요한 구분:

- Fine-tuning에는 tokenization이 필수입니다.
- Embedding/vectorization은 fine-tuning의 필수 단계가 아닙니다.
- Vectorization은 RAG, semantic search, evidence retrieval을 위한 별도 데이터 경로입니다.

## 4. Candidate Data Sources

공개 데이터셋 후보의 조사 상태, license/terms, raw malware 포함 가능성, Phase D/E 적용 여부는 [DATASET_CANDIDATES.md](DATASET_CANDIDATES.md)에 기록합니다. 이 섹션은 데이터 소스의 원칙적인 사용 방향만 유지합니다.

| Source | Primary use | Allowed in Git | Notes |
| --- | --- | --- | --- |
| NVD / CVE metadata | fine-tuning, evaluation, prompt examples | small curated fixtures only | CVE description, CVSS, CWE, affected products, references를 정규화 후보로 둔다. |
| CISA KEV catalog | evaluation, risk prioritization examples | small curated fixtures only | known exploited 여부와 due date는 risk prioritization 학습에 유용하다. |
| MITRE ATT&CK STIX/TAXII | RAG/vector, mapping evaluation, controlled labels | small mapping fixtures only | tactic, technique_id, technique_name을 정규화 기준으로 둔다. |
| Public CTI reports | RAG/vector, summarization examples, evaluation candidates | no raw full reports by default | 긴 문서이므로 chunking과 licensing 확인이 필요하다. |
| Project NuriLab normalized static analysis output | fine-tuning, evaluation, prompt examples | synthetic or redacted fixtures only | AegisLM과 Project NuriLab을 연결하는 가장 중요한 내부 데이터 후보. |
| Synthetic suspicious script metadata | tiny dataset, validation fixtures | yes, if non-operational and safe | 실제 악성 실행 절차가 아니라 정적 분석용 metadata 중심으로 작성한다. |
| VirusTotal reports/metadata | enrichment, evaluation candidates | no by default | API terms, quota, redistribution 가능 여부를 확인한 뒤 사용한다. |
| MalwareBazaar metadata | enrichment, evaluation candidates | metadata-only curated fixtures only | 실제 sample download/storage는 v0 범위 밖이다. |

## 5. Source Format Differences

대부분의 보안 플랫폼은 JSON 또는 JSON에 가까운 기계 판독 형식을 제공하지만, 구조와 의미는 서로 다릅니다. 원본 JSON을 그대로 fine-tuning 데이터로 쓰지 않고, AegisLM 공통 record shape로 정규화해야 합니다.

| Source | Data character | Format pattern | AegisLM interpretation |
| --- | --- | --- | --- |
| NVD CVE | 취약점 메타데이터 | CVE 중심의 중첩 JSON | 취약점 설명, severity, CWE, affected products, references를 이해한다. |
| CISA KEV | 실제 악용된 취약점 목록 | 비교적 flat한 catalog JSON/CSV | known exploited 여부, 조치 우선순위, due date를 이해한다. |
| MITRE ATT&CK | 공격 기법 지식베이스 | STIX 2.1 JSON bundle과 relationship graph | tactic, technique_id, technique_name, mitigation/detection을 매핑 기준으로 사용한다. |
| VirusTotal | 파일/URL/IP/domain 분석 메타데이터 | JSON:API 스타일 object 구조 | hash, reputation, detection result, tag, relationship metadata를 참고한다. |
| MalwareBazaar | 악성 샘플 메타데이터 | query response 중심 JSON | hash, signature, tag, family, first_seen 같은 metadata만 참고한다. |
| Public CTI report | 자연어 보안 보고서 | HTML, PDF, Markdown, blog text 등 비정형 | 요약, chunking, RAG/evidence retrieval 후보로 본다. |

데이터 소스별로 답하는 질문도 다릅니다.

- NVD는 "이 CVE가 무엇이고, 어떤 취약점 속성을 갖는가?"에 답한다.
- CISA KEV는 "이 CVE가 실제로 악용되었고, 얼마나 우선 조치가 필요한가?"에 답한다.
- MITRE ATT&CK는 "관찰된 행위가 어떤 tactic/technique에 해당하는가?"에 답한다.
- VirusTotal과 MalwareBazaar는 "이 파일, hash, URL, domain이 어떤 평판과 metadata를 갖는가?"에 답한다.
- Public CTI는 "사건, 캠페인, 취약점, 행위가 어떤 맥락으로 설명되는가?"에 답한다.

AegisLM의 데이터 전략은 원본 구조를 외우는 것이 아니라, 각 원천 데이터가 어떤 질문에 답하는지 이해하고 필요한 필드만 공통 record로 변환하는 것입니다.

초기 학습 순서:

1. NVD CVE 5개를 직접 읽고 필드 구조를 이해한다.
2. CISA KEV 5개를 NVD CVE와 매칭해 같은 CVE라도 어떤 정보가 다른지 본다.
3. MITRE ATT&CK technique 5개를 읽고 tactic, technique_id, description, detection, mitigation 구조를 이해한다.
4. VirusTotal과 MalwareBazaar는 실제 sample download 없이 metadata 구조만 확인한다.
5. 위 내용을 AegisLM 공통 record shape에 어떻게 매핑할지 정한다.

이 단계의 목표는 데이터를 많이 받는 것이 아닙니다. 데이터의 의미를 이해하고, 어떤 필드가 fine-tuning, evaluation, RAG/vector 경로에 필요한지 결정하는 것입니다.

## 6. Safety and Exclusion Policy

다음 데이터는 Git에 저장하지 않습니다.

- 실제 악성 샘플
- executable malware payload
- packed binary, script payload, exploit payload
- secrets, API keys, tokens, passwords
- private CTI
- private customer data
- 민감한 내부 코드
- raw downloaded datasets
- model checkpoint
- adapter artifact

다음 내용은 fine-tuning target output에 포함하지 않습니다.

- 공격 실행 절차
- 우회 로직
- credential theft workflow
- persistence instruction
- exploit execution step
- malware deployment or evasion guidance

AegisLM 학습 데이터는 방어적 분석 목적이어야 합니다. 모델은 최종 보안 판단자가 아니라 설명, 요약, TTP 매핑, 우선순위화, 구조화 출력을 담당합니다.

## 7. Sample Unit

v0에서 우선 고려할 sample unit은 다음과 같습니다.

| Unit | Use | v0 decision |
| --- | --- | --- |
| One static analysis result | primary fine-tuning unit | 기본 단위 후보 |
| One CVE record | vulnerability context examples | 보조 단위 |
| One CISA KEV entry | risk prioritization examples | 보조 단위 |
| One ATT&CK technique | mapping and label reference | evaluation/RAG 중심 |
| One CTI section or paragraph | summarization/RAG examples | chunking 후 사용 |
| One synthetic suspicious script metadata item | tiny dataset and tests | Phase C fixture 후보 |

Phase C의 기본 방향은 `raw file`이 아니라 `normalized analysis record`를 학습 샘플 단위로 삼는 것입니다.

## 8. Record Shape Draft

Fine-tuning 또는 tiny dataset record는 아래 방향으로 설계합니다.

```json
{
  "id": "string",
  "source": {
    "type": "nvd|cisa_kev|mitre_attack|public_cti|nurilab_synthetic|nurilab_analysis",
    "name": "string",
    "url": "string|null",
    "license_or_terms": "string|null",
    "retrieved_at": "YYYY-MM-DD|null"
  },
  "input": {
    "task": "string",
    "context": "string",
    "signals": {}
  },
  "expected_output": {},
  "metadata": {
    "split": "train|validation|test|fixture",
    "safety_level": "metadata_only|synthetic|redacted|restricted",
    "contains_executable_payload": false,
    "notes": []
  }
}
```

이 구조는 Phase C의 초안입니다. JSON output contract와 validation test를 작성하면서 좁혀갑니다.

## 9. Preprocessing Policy

전처리는 원천 데이터의 의미를 보존하면서 학습에 불필요하거나 위험한 정보를 제거하는 과정입니다.

기본 규칙:

- source, provenance, retrieved_at을 유지한다.
- CVE, CWE, CVSS, ATT&CK technique_id는 표준 표기법으로 정규화한다.
- HTML은 plain text 또는 safe Markdown으로 정리한다.
- 중복 문단, boilerplate, navigation text는 제거한다.
- secrets, credentials, private identifiers는 제거한다.
- 실행 가능한 payload, exploit step, evasion instruction은 제거하거나 샘플에서 제외한다.
- code snippet은 방어적 정적 분석에 필요한 최소 metadata로 축약한다.
- raw data와 processed data의 경계를 명확히 기록한다.

## 10. Tokenization and Chunking

Tokenization은 fine-tuning에 필수입니다. 텍스트를 기준 모델 tokenizer의 token id로 변환해 학습하기 때문입니다.

Chunking은 긴 문서나 긴 분석 결과를 다룰 때 필요합니다. 모든 데이터에 무조건 적용하지 않습니다.

Phase C token budget 초안:

| Area | Draft budget |
| --- | --- |
| input context | 2,000-4,000 tokens |
| expected JSON output | 500-1,000 tokens |
| total training example | 3,000-6,000 tokens |

이 수치는 v0 초안입니다. `openai/gpt-oss-20b` tokenizer와 실제 GPU memory behavior를 확인한 뒤 조정합니다.

Chunking 기준:

- CTI report는 section 단위가 우선이고, paragraph chunking은 보조로 사용한다.
- Project NuriLab analysis output은 rule finding, file metadata, suspicious behavior group 단위로 축약한다.
- CVE/KEV record는 보통 chunking하지 않는다.
- ATT&CK technique reference는 technique 단위로 유지한다.
- chunk overlap은 RAG에는 사용할 수 있지만 fine-tuning examples에는 기본 적용하지 않는다.
- chunk마다 source_id, section_id, original_url, retrieved_at을 유지한다.

너무 긴 샘플 처리 순서:

```text
remove boilerplate
-> retain security-relevant fields
-> summarize non-critical context
-> split by section
-> reject if still too long or unsafe
```

## 11. Vectorization Policy

Vectorization은 Phase C fine-tuning 필수 작업이 아닙니다.

Vectorization을 도입하는 경우는 다음으로 제한합니다.

- ATT&CK technique reference 검색
- CVE/KEV 관련 근거 검색
- 긴 CTI report에서 관련 section 검색
- Project NuriLab 분석 결과와 외부 reference 연결

RAG/vector 데이터는 fine-tuning 데이터와 별도 저장소 또는 별도 artifact path에서 관리합니다. embedding index는 Git에 저장하지 않습니다.

## 12. Split and Contamination Policy

Phase C tiny dataset은 매우 작기 때문에 formal split보다 fixture 역할이 우선입니다.

Phase D/E 이후에는 다음 기준을 적용합니다.

- train/validation/test를 분리한다.
- 같은 CVE에서 파생된 record는 같은 split에 둔다.
- 같은 CTI report에서 나온 chunk는 같은 split에 둔다.
- 같은 Project NuriLab synthetic scenario에서 나온 변형 record는 같은 split에 둔다.
- evaluation fixture는 학습 데이터에 포함하지 않는다.
- held-out examples는 실험 결과 비교 전 고정한다.

초기 split 초안:

| Dataset size | Suggested split |
| --- | --- |
| 5-20 examples | fixture only, no formal split |
| 50-200 examples | train/validation/test = 70/15/15 |
| 200+ examples | grouped split by source family, CVE, report, or scenario |

## 13. Tiny Dataset Acceptance Criteria

Phase C의 tiny dataset은 성능 향상 목적이 아니라 schema와 validation 흐름 검증 목적입니다.

최소 조건:

- 5-20개 수준
- metadata-only 또는 synthetic 중심
- 실제 악성 샘플 없음
- executable payload 없음
- 정상/악성 유사/불확실/unknown 계열 사례 포함
- JSON output contract 검증에 필요한 필드 포함
- unsafe guidance 실패 fixture 포함
- source/provenance/safety metadata 포함

Phase C tiny dataset이 통과해야 할 질문:

- 이 record를 Git에 저장해도 안전한가?
- 이 record가 fine-tuning/evaluation/RAG 중 어떤 목적을 갖는가?
- 이 record는 너무 길지 않은가?
- 이 record의 expected output이 JSON contract를 검증하는 데 도움이 되는가?

## 14. Phase C Deliverables

Phase C 완료 전 산출물:

- `docs/DATA_STRATEGY.md`
- `docs/TEST_CRITERIA.md`
- JSON output contract draft
- tiny dataset fixture
- schema validation test
- unsafe/malformed fixture test

Phase C에서 하지 않는 일:

- 대형 dataset download
- 실제 악성 샘플 저장
- GPU fine-tuning run
- model checkpoint 또는 adapter artifact 생성
- RAG embedding index 생성

## 15. Reference Links

- NVD Data Feeds: https://nvd.nist.gov/vuln/Data-Feeds/
- NIST NVD: https://www.nist.gov/itl/nvd
- CISA KEV Catalog: https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- MITRE ATT&CK Data & Tools: https://attack.mitre.org/resources/attack-data-and-tools/
- MITRE CTI Repository: https://github.com/mitre/cti
- VirusTotal API Overview: https://docs.virustotal.com/docs/api-overview
- VirusTotal quota documentation: https://docs.virustotal.com/docs/consumption-quotas-handled
- MalwareBazaar API: https://bazaar.abuse.ch/api/
- Hugging Face Dataset Cards: https://huggingface.co/docs/hub/datasets-cards

## 16. Initial Tiny Fixture Implementation

Phase C의 첫 tiny fixture는 성능 학습 목적이 아니라 schema와 validation 흐름 검증 목적이다.

초기 fixture 기본값:

- format: JSONL
- location: `tests/fixtures/tiny_phase_c_records.jsonl`
- size: 5 records
- source mix: CVE metadata, CISA KEV metadata, MITRE ATT&CK mapping reference, synthetic safe static-analysis metadata
- split: `fixture`
- safety: `metadata_only` 또는 `synthetic`
- executable payload: always `false`

첫 fixture 세트는 다음 케이스를 포함한다.

- KEV critical deserialization case
- KEV ransomware-known metadata case
- non-KEV high-CVSS case
- KEV ambiguous mapping case with empty `attack_mapping`
- synthetic low-risk static-analysis metadata case
