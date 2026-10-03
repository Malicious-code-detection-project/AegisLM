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

Model adapter, checkpoint, model card, and evaluation artifact storage rules are maintained in [ARTIFACT_STORAGE_POLICY.md](ARTIFACT_STORAGE_POLICY.md).

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
- `tests/fixtures/heldout_evaluation_records.jsonl`은 Phase D/E adapter 비교용 `test` split fixture로 관리하며 adapter training data에 절대 포함하지 않는다.

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
- held-out evaluation fixture는 train/validation fixture와 ID가 겹치지 않아야 한다.
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


## 17. Held-out Evaluation Fixture

Phase D/E의 adapter 비교에는 `tests/fixtures/heldout_evaluation_records.jsonl`을 사용한다. 이 fixture는 `metadata.split: "test"`로 두며, training 또는 validation 샘플로 재사용하지 않는다.

필수 구성:

- benign synthetic case
- KEV exploited vulnerability case
- non-KEV high severity case
- ambiguous ATT&CK mapping case with empty `attack_mapping`
- safety refusal evaluation candidate

모든 record는 metadata-only 또는 synthetic이어야 하며, 실제 악성 샘플, executable payload, secrets, private CTI를 포함하지 않는다.

## 18. Phase E Source-v2 Frozen Dataset

The current C/C++ fine-tuning experiment uses the Git-ignored processed dataset
at data/processed/phase-f-source-v5-r1.

| Split | Count | Model-visible shape | Purpose |
| --- | ---: | --- | --- |
| train | 10,000 | system/user/assistant | QLoRA training |
| validation | 1,000 | system/user/assistant | loss and canary gates |
| challenge | 500 | system/user only | primary base/adapter comparison |
| gold | 500 | id/expected_output | post-inference scoring only |

Train and validation are balanced 50/50 between present and not_observed. The
2026-09-10 full audit recalculated source SHA-256 values rather than trusting
declared hashes and found no ID or source overlap between train, validation,
and challenge. All 11,000 supervised outputs and all 500 challenge/gold pairs
passed their source-v2 schema, target-CWE, and exact-substring evidence checks.

Known quality limitations are recorded rather than hidden:

- assistant response wording is highly templated and duplicated
- confidence values are effectively all high
- supervised splits do not teach meaningful uncertain behavior
- primary challenge may have been visible while the data pipeline was
  developed, so it is held out from training but not claimed as untouched blind

phase-f-source-untouched-blind-480-v1 is a secondary label-only comparison. Its
compact gold cannot support evidence-span scoring and must not be merged with
primary full-report metrics.

Processed datasets remain outside Git. Only loaders, validators, frozen
configuration, tests, and aggregate audit results belong in the repository.

Before any source-v2 record can enter evaluation or the W&B source-free table,
its ID must match `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$` and `target_cwe` must
match `^CWE-[1-9][0-9]*$`. These domains prevent source text, paths, and other
unbounded strings from being reclassified as safe identifiers.

## C/C++ raw-source reconstruction (2026-09-28)

`scripts/build_cc_source_corpus.py` creates a new local candidate corpus from
`data/raw_data`; it does not overwrite the previous Q1R10/Q1R11 datasets or
automatically start training. Run with the locked `data-prep` dependency group:

```bash
uv run --group data-prep python scripts/build_cc_source_corpus.py \
  --output data/processed/cc-source-candidates-20260928-v1 --seed 3407
```

The canonical JSONL unit is a function with `id`, `group_id`, `split`,
`language`, `source_code`, `target_cwe`, `assessment`, `evidence_ranges`,
`hashes`, `provenance`, and `annotation`. Missing CWE or labels remain null;
multiple source CWEs remain in `annotation.cwe_candidates` rather than being
arbitrarily assigned as positive function-level labels. Original locations and
source IDs stay in provenance and never enter model-visible messages.

- PrimeVul, DiverseVul, BigVul and Juliet source labels are retained as
  `source_label_unreviewed`, not upgraded to verified scoped-CWE decisions.
- BigVul after-change functions, CVEfixes methods and DecompileBench source
  functions are retained for review without invented binary labels. CVEfixes
  can use the hash-verified read-only SQLite cache of the earlier SQL import.
- Assemblage is inspected for complete function source; empty `source_codes`
  cannot supply this task. ARVO metadata, chat QA, binary features and pretrained
  benchmark models are inventoried with explicit exclusion reasons.
- Evidence remains null and `evidence_status=unreviewed` until independently
  annotated. Changed lines are not treated as evidence, fixed functions are not
  automatically negatives, and confidence is not fabricated.
- Source comments are removed, preserving line structure. Juliet good/bad/CWE
  identifiers are neutralized. Line annotations must reference the final stored
  code, not the original raw-file coordinates.

`pool/*.jsonl` preserves normalized candidates, including unlabeled records.
`canonical/{train,validation,test}.jsonl` contains exactly 10,000/1,000/500
selected provisional records, balanced between source positive and negative
labels. `decision-candidates/` contains system/user/assistant exports for train
and validation, plus separate test `challenge.jsonl` and `gold.jsonl`.
`review/evidence-pending.jsonl` tracks the outstanding annotation work; there
is no evidence SFT export until real line-level gold exists. Completion of
conversion does not authorize training: the manifest keeps
`approved_for_training=false` and records the unresolved semantic review.

Before seed-based sampling, connect records through repository/function family,
CVE, commit, lexical identity and identifier-normalized lexical identity.
Conservatively merge repository basenames across providers when identifying a
function family. Juliet uses testcase families across numbered variants.
A group belongs to one split only. Empty stubs and functions below the selectable
25-token minimum do not connect unrelated projects through clone hashes. Whole
repositories are not required to be disjoint: shared code can otherwise collapse
most projects into one component. The final lexical clone audit still applies.
Conflicting source labels on identical lexical code are excluded. Previously
used `phase-f-source-*` train/validation/challenge artifacts are read directly;
components touching their lexical fingerprints are excluded from the new selection.
The original public split names are retained in provenance but this new split is
not presented as an official PrimeVul/BigVul/DiverseVul benchmark.

Check final cross-split near clones by an exact prefix-filtered Jaccard join of
identifier-normalized token 5-grams at similarity >= 0.8. Merge detected groups
and resample with the same seed until none remain; do not select by model scores.
This is a stated lexical-clone test, not proof of arbitrary semantic independence.
Re-read final JSONL files and recompute IDs, hashes, groups, historical overlaps,
and near-clone overlaps. Save split audit, source counts, input hashes and output
SHA-256 inventory. Refuse an existing output directory or an insufficient pool.
The initial 80/10/10 hash buckets are candidate supplies rather than exact output
counts. If parsing/exclusions exhaust one supply, assign previously unused whole
groups in deterministic seed order. A group already selected for another split
cannot be reassigned. Preserve 50/50 labels and the exact requested output sizes;
record reserve-group allocations in the audit. No model scores inform selection.

`--reuse-pool <prior-output>` can reuse a completed normalization stage in a new
output directory. It refuses an active SQLite journal and inconsistent pool row
counts. Input manifests fingerprint the reused pool and index as well as original
source files. An intermediate normalization directory without a final manifest
is not a completed split dataset.

`--exclude-ids <json-array>` records explicit exclusions, such as token-budget
failures, in the input manifest and split audit; it accepts only IDs present in
the selectable pool. Rebuild into a new directory after exclusion. Do not truncate
code or edit a frozen test file in place to satisfy a context-length limit.

Selected functions must parse as one C/C++ function and meet a lexical size
limit. This is not a tokenizer budget check; model-specific tokenization and
assistant-only loss-mask checks remain required before training.

### Materialized candidate result

The final current artifact is `data/processed/cc-source-candidates-20260928-v5`.
The reusable normalization pool, originally in `cc-source-candidates-20260928-v1/pool`,
now lives at `data/cache/cc-source-normalized-20260928/pool` after the verified
2026-10-02 relocation. It contains 1,012,598 records from six providers. v2-v4
were intermediate attempts and have been removed after preserving evidence.
The v5 source distribution is:

| Source | Train | Validation | Test |
| --- | ---: | ---: | ---: |
| PrimeVul | 3,315 | 368 | 198 |
| DiverseVul | 3,259 | 367 | 174 |
| BigVul | 3,281 | 260 | 128 |
| Juliet | 145 | 5 | 0 |
| Total | 10,000 | 1,000 | 500 |

Each split has equal positive/negative source-label counts. CVEfixes and
DecompileBench remain in the normalized pool without inferred scoped labels.
All final split overlap metrics are zero, including the stated near-clone test
and historical lexical fingerprints. Identical lexical code with contradictory
source labels (3,009 hashes) was excluded from selection. Project/function, CVE
and commit grouping are independently recomputed on the final canonical files
by the builder (this is not an independent reviewer approval).

The actual pinned Unsloth GPT-OSS tokenizer and `tokenize_source_training_record`
formatter (`reasoning_effort=low`, frozen date 2026-09-28, empty-analysis/final)
give maximum lengths 4,055/3,772/2,947 for train/validation/test. Every record has
16-18 supervised tokens; none exceeds 4,096. Eleven overlength IDs were excluded
without truncation before the final split was frozen. Token counts from the base
tokenizer alone are not the authoritative training-format audit.

Audit scripts and results are under `outputs/cc-source-candidates-20260928-v5`.
The output SHA-256 list and canonical/messages alignment pass. Unit suite:
450 passed; Ruff lint/format and mypy pass. Training readiness is still false:
scoped CWE labels require semantic review, evidence gold is absent, and the
evidence SFT export has zero records. Test CWE-93 has no training CWE-93 records;
the split is not claimed to be stratified by every rare CWE.

Exact selection replay (choose an unused output directory):

```bash
uv run --offline --frozen --group data-prep python scripts/build_cc_source_corpus.py \
  --reuse-pool data/cache/cc-source-normalized-20260928 \
  --exclude-ids outputs/cc-source-candidates-history-20260929/reproduction/exclude-overlength-ids.json \
  --output outputs/cc-source-candidates-replay --seed 3407
```

### 시도 이력과 학습 전 정리 결정 (2026-09-29)

사용자 결정: 시도·실패·수정 근거를 문서화하고, **학습 시작 전에 중간
산출물을 정리한다.** 운영 학습/평가 입력은 최종 v5의 분할만 사용한다.
아래는 당시 실제 실행 결과다. 2026-09-29에는 삭제하지 않았으며,
2026-10-02의 이관·삭제 완료 기록은 다음 절에 추가했다.

| 버전 | 시도와 관측 결과 | 다음 수정 / 재발 방지 |
| --- | --- | --- |
| v1 | 여섯 원천 1,012,598건 정규화 완료. 저장소 전체와 복제 코드의 연결이 지나치게 커짐. PrimeVul 중간 검사에서 약 94%가 한 연결 그룹이었고, 최종 학습 양성 공급은 388/5,000건에 그쳐 분할 실패. | 저장소 전체 대신 프로젝트 내 함수 계열·CVE·커밋·복제 코드로 연결. 25토큰 미만의 짧은 함수는 복제 지문으로 무관한 프로젝트를 연결하지 않음. 최종 분할의 복제 검사는 유지. |
| v2 | 수정된 그룹 기준을 적용했으나 제외·구문 검사 후 검증 양성이 447/500건으로 부족. | 이미 선택한 그룹을 다른 분할로 옮기지 않고, 아직 사용하지 않은 그룹만 고정 seed 순서로 추가 배정. |
| v3 | 10,000/1,000/500 및 중복 검사 통과. 첫 유사 코드 검사에서 한 쌍을 찾아 같은 그룹으로 합친 후 재추출. 기본 GPT-OSS tokenizer 검사에서 학습 9건·테스트 1건이 4,096토큰 초과. | 코드 잘림 대신 해당 10개 ID를 제외하고 재추출. 분할 통과와 모델별 토큰 통과를 구분. |
| v4 | 10건 교체 후 분할 검사 통과. 실제 pinned Unsloth tokenizer와 학습 formatter를 적용하니 학습 1건이 4,108토큰으로 추가 초과. | 모델 이름만 같다고 템플릿이 같다고 가정하지 않음. 실제 학습 tokenizer revision·reasoning·empty-analysis/final 포맷으로 재검사. |
| v5 | 누적 11개 ID 제외 후 최종 분할·export 정합성·중복·토큰 검사 통과. 최대 토큰 4,055/3,772/2,947. 모든 레코드의 supervised token 16–18개. | 최종 기준본으로 유지. 라벨 의미 검수와 근거 줄 검수는 미완료 상태 그대로 기록. |

보조 검사에서 확인한 실수도 남긴다.

- Transformers 5의 `apply_chat_template` 반환 객체에 `len()`을 바로 적용해
  토큰 수 대신 키 개수 2를 셌던 결과는 **무효**다. 당시 파일명은
  `token-audit-invalid-key-count.json`이며 성공 근거로 사용하지 않는다.
  실제 `input_ids` 길이를 확인하고, 최종 검사는 학습 formatter의
  `features["input_ids"]`와 `labels`를 사용했다.
- 프로젝트의 weights cache에는 Unsloth tokenizer 파일이 완비되지 않았다.
  base tokenizer로 대체하면 padding/템플릿 계약이 달라진다.
  최종 검사에서는 `resolve_fresh_tokenizer_snapshot`으로 기본 HF cache에
  있는 revision `093fba6992ef5a7152481afec0bdfca1ac486998`의 완전한 snapshot을
  찾아 사용했다. 캐시 파일 부재를 tokenizer 변환 패키지 설치 문제로 오인하지 않는다.
- 기본 tokenizer의 길이 검사만으로 실제 학습 formatter 통과를 주장하지 않는다.
  코드 파싱, 분할, 토큰 길이, loss mask 검사는 의미 라벨/근거의 정확성을
  보장하지 않는다. 현재 `approved_for_training=false`를 유지한다.

#### 보존한 근거

Git에 남기는 정본은 이 문서의 방법·결정·집계 결과와 빌더/테스트/의존성
설정이다. 원본 코드와 대형 데이터는 계속 Git 밖에 둔다.
작은 실행 근거 묶음은 `outputs/cc-source-candidates-history-20260929`에
보관했다. 52개 파일을 복사하고 SHA-256을 대조했으며 다음을 포함한다.

- v1-v5의 가용 manifest, 입력 hash 목록, 분할 검사, 제외 ID, 토큰 검사,
  export 검사, `/tmp`에 있던 실행 로그 및 초기 v1 빌더.
- 최종 빌더·정규화/분할 모듈·테스트·의존성 lock·학습 포맷 관련 코드 snapshot.
- `archive-manifest.json`: 원래 경로와 보관 경로, 크기, SHA-256, 보관 한계.
- `SHA256SUMS`: 보관 파일 검증 목록.

v2-v4의 당시 코드 전체 snapshot은 남아 있지 않다. 존재하는 command/hash/
검사/로그만 보존했으며, 완전한 과거 코드가 복원됐다고 주장하지 않는다.
v1의 초기 빌더는 있지만 당시 companion 모듈의 별도 snapshot도 없다.

#### 학습 직전 정리 순서와 범위

기존 `data/processed` 83개 폴더까지 확장한 목록과 참조 의존성은
[폴더 이력 및 정리 기록](DATASET_ARTIFACT_INVENTORY.md)에 보존한다.
해당 문서의 정리 후보 표기는 삭제 완료나 신규 학습 승인으로 해석하지 않는다.

1. **최종본 확인:** v5의 파일 수·SHA-256·분할·토큰 검사와 검수 상태를 확인한다.
   의미 검수를 완료한 후속 release가 있다면 v5와의 변경 이력 및 split 소속을
   먼저 고정한다. Base/adapter 비교는 동일한 최종 test 500건을 사용한다.
2. **재생성 의존성 해소:** v5 생성 명령은 현재 v1의 `pool/`, `index.sqlite`,
   `inventory.json`, `normalization_counts.json`과
   `outputs/cc-source-candidates-20260928-v4/exclude-overlength-ids.json`을 참조한다.
   제외 ID 사본은 history 묶음의 `reproduction/`에도 보존했다.
   정규화 cache를 별도 보존 위치로 이관하거나 원본으로부터 재생성하고,
   새 경로로 최종 선택 결과가 재현되는지 확인한 뒤 기존 의존 폴더를 정리한다.
   재현 검증이 안 된 cache를 단순 중간 파일로 간주해 먼저 삭제하지 않는다.
3. **과거 데이터 중복 검사 의존성 보존:** 빌더는 기존 `phase-f-source-*`의
   실제 train/validation/challenge 파일도 읽는다. 이 파일들은 이번 정리
   대상이 아니다. 향후 별도로 정리하려면 제외 지문과 입력 hash·추출 방법을
   먼저 보존하고 동일한 제외 결과를 검증한다.
4. **문서·검사 기록 유지:** history 묶음과 Git 문서를 검증한다. 이동 시에는
   원래 경로/새 경로/hash를 별도 이관 기록에 남긴다. 기존 frozen manifest를
   수정해 과거 경로를 지우거나 SHA-256을 다시 작성하지 않는다.
5. **중간 산출물 정리:** 위 조건을 충족한 `cc-source-candidates` v1-v4의
   중복/실패 데이터와 보관 완료된 임시 실행 파일을 정리한다. 활성 학습 입력으로
   최종본 하나만 보이게 하고, 유지해야 하는 cache·history는 역할이 드러나는
   보존 경로로 분리한다. 각 정리 대상의 원래 경로·처리 내용·시점을 기록한다.
6. **정리 후 확인:** 최종 train/validation/test 및 challenge/gold가 여전히
   열리고 수량·해시가 일치하는지, 실행 명령의 입력 경로가 모두 유효한지 확인한다.

이번 범위에는 `raw_data`, 모델·어댑터·checkpoint, 다른 실험 결과, 기존
Q1R10/Q1R11 원본 데이터의 일괄 삭제가 포함되지 않는다. 최종 기준 데이터와
검사 기록도 삭제 대상이 아니다. 학습 직전 정리 완료 기록이 생기기 전에는
문서만 갱신했다고 정리 작업이 끝났다고 표시하지 않는다.


### 2026-10-02: 재생성 의존성 이관 및 중간 폴더 정리 완료

사용자가 재개한 1단계(보존 및 정리)를 완료했다. 학습 설정 연결·커밋·푸시·GPU 학습은
이번 단계에서 실행하지 않았다. 2026-09-29의 원래 결정과 frozen artifact는 유지한다.

| 처리 대상 | 완료한 처리 | 보존/검증 근거 |
| --- | --- | --- |
| `data/processed/cc-source-candidates-20260928-v1` | `data/cache/cc-source-normalized-20260928`로 같은 파일시스템 내 이관 | pool 6개, index, inventory, counts 총 9개 파일 해시 일치; 약 2.39 GiB 보존 |
| v4 검사 폴더의 `exclude-overlength-ids.json` | 현재 재현 명령은 history의 `reproduction/` 사본 사용 | 11개 ID, 원본과 사본 SHA-256 일치 |
| `data/processed/cc-source-candidates-20260928-v2/v3/v4` 각각 | metadata·해시 보존 후 삭제 | 이관 입력으로 최종 v5를 먼저 재현 |
| `outputs/cc-source-candidates-20260928-v3/v4` 각각 | 검사 스크립트·보고서·제외 목록 보존 후 삭제 | 새 cleanup 묶음의 `metadata-before/`와 기존 history에 보존 |
| cleanup 작업의 임시 `replay/` | 비교 후 임시 데이터 삭제 | 실제 재생성 명령·로그·파일 해시·replay metadata·export 검사 보존 |
| 최종 v5 | 원본 경로와 바이트 유지 | 정리 전/후 전체 파일 해시와 export 정합성 재검증 |

삭제한 기존 중간 폴더는 5개(데이터 3개, 검사 2개), 파일 크기 합계는 **121.56 MiB**다.
v1은 삭제가 아니라 이관이다. 이 값은 metadata 보존 공간을 차감한 순수 회수 용량이 아니다.
`data/processed`의 전체 폴더 수는 83 → 79이며, 새 `cc-source-candidates-*` 폴더는
최종 v5 하나다. 그 외 과거 source 데이터는 중복 제외 입력으로 계속 보존한다.

#### 실제 재현 및 정리 후 검사

- 새 캐시와 보존한 제외 목록을 사용해 seed 3407로 전체 선택·분할 과정을 재실행했다.
- 원래 v5와 **11개 파일이 바이트 단위로 일치**했다: canonical 3개,
  decision-candidates 4개, evidence-pending 1개, inventory/counts/split-audit 3개.
- `input-manifest` 26,942개 항목은 캐시·제외 파일의 경로 이관을 대응시키면 크기·해시가 동일했다.
  manifest에서 바뀐 것은 재현 command와 normalized_pool_path뿐이다.
  재현 manifest/input-manifest/SHA256SUMS는 원래 frozen metadata와 다른 파일이며 덮어쓰지 않았다.
- 재현 및 최종본의 export/SHA 검사는 모두 통과했다. 최종 train/validation/test는
  10,000/1,000/500, 각 라벨 50/50이며 challenge 입력과 gold는 분리된다.
- 기존 토큰 검사(날짜 2026-09-28, pinned Unsloth formatter)의 입력 해시는 현재 최종 파일과
  동일하다. 이번 경로 정리는 토큰화를 다시 실행하지 않았다. 다음 단계에서 실행 날짜·formatter가
  바뀌면 해당 조건의 토큰 검사를 다시 해야 한다.
- 의미 라벨/근거 검수 상태와 `approved_for_training=false`는 유지한다.

실제 명령은 위의 현재 재현 명령과 동일한 입력이며 output만
`outputs/cc-source-cleanup-20261002/replay`였다. 그 임시 경로는 검사 후 삭제했다.
현재 재현 입력은 유효하고, 원래 frozen manifest의 옛 경로는 이관 기록으로 해석한다.

완료 증거는 Git 제외 `outputs/cc-source-cleanup-20261002/`에 보존했다:
`cleanup-manifest.json`, `reproduction-audit.json`, `final-export-audit.json`,
`replay-export-audit.json`, 실행 로그·정리 스크립트·metadata 사본·`SHA256SUMS`.
기존 history 묶음 52개 파일의 해시도 정리 전에 확인했다.
CVEfixes DB의 과거 검증 해시는 재현 builder가 재사용했으며 이번에 DB 전체를 다시 해시하지 않았다.
