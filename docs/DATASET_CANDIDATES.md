# Dataset Candidates

이 문서는 `AegisLM` Phase D/E 이후에 검토할 공개 데이터셋 후보를 기록합니다.

`docs/DATA_STRATEGY.md`가 데이터 사용 원칙과 안전 정책의 정본이라면, 이 문서는 외부 데이터셋 후보의 조사 상태와 AegisLM 적용 가능성을 추적하는 registry입니다.

이 문서는 실제 데이터 다운로드 목록이 아닙니다. 후보의 출처, 라이선스/이용 조건, 데이터 타입, raw malware 포함 가능성, AegisLM 사용 목적을 먼저 검토하기 위한 문서입니다.

## 1. Scope

이 문서에서 다루는 항목:

- 공개 CTI, 악성코드 분석 텍스트, malware family label, PE metadata, feature vector, benchmark dataset 후보
- fine-tuning, evaluation, benchmark, RAG/vector 용도 분류
- raw malware 포함 가능성 및 Git 저장 가능 여부 판단
- Phase D/E에서 우선 검토할 1차 후보

이 문서에서 다루지 않는 항목:

- 실제 데이터 다운로드
- raw malware sample 수집
- dataset 변환 스크립트 구현
- fine-tuning 실행 결과
- benchmark 점수 주장

## 2. Safety Rules

다음 항목은 이 저장소에 커밋하지 않습니다.

- 실제 악성 샘플
- executable malware payload
- packed binary, script payload, exploit payload
- raw downloaded dataset dump
- model checkpoint
- adapter artifact
- secrets, API keys, tokens, passwords
- private CTI
- private customer data

데이터셋 후보를 검토할 때는 다음 순서를 따릅니다.

1. source URL과 maintainer를 확인한다.
2. license 또는 terms of use를 확인한다.
3. raw malware binary 포함 여부를 확인한다.
4. Git 저장 가능 범위와 외부 artifact 저장 필요 여부를 분리한다.
5. AegisLM record shape로 변환 가능한 필드를 식별한다.
6. fine-tuning, evaluation, benchmark, RAG/vector 경로 중 어디에 사용할지 정한다.
7. 안전하지 않거나 범위가 큰 항목은 `hold` 또는 `avoid`로 둔다.

## 3. Usage Tags

| Tag | Meaning |
| --- | --- |
| `sft-candidate` | supervised fine-tuning 예시로 변환할 수 있는 후보 |
| `evaluation-candidate` | held-out fixture 또는 평가 기준으로 사용할 수 있는 후보 |
| `benchmark-candidate` | baseline/adaptor 비교를 위한 외부 benchmark 후보 |
| `metadata-evaluation` | raw sample 없이 hash, label, static feature, report metadata 중심으로 평가 가능한 후보 |
| `rag-candidate` | retrieval/vector index의 근거 문서 후보 |
| `hold` | 추가 법적/운영적 검토 전까지 보류 |
| `avoid` | v0 범위에서 사용하지 않는 것이 적절한 후보 |

## 4. First-Pass Candidates

| Candidate | Source type | Data type | Current use tags | Git policy | Notes |
| --- | --- | --- | --- | --- | --- |
| APTNotes | GitHub, public report index | APT/CTI report metadata, report links, CSV/JSON summaries | `sft-candidate`, `rag-candidate`, `evaluation-candidate` | Link and small metadata fixture only | Public APT/campaign reports are useful for summarization, evidence extraction, and ATT&CK mapping tasks. Full report redistribution and license terms must be checked per source. |
| MalwareTextDB | academic dataset | annotated malware-related text | `sft-candidate`, `evaluation-candidate` | Small curated fixture only after license review | Useful for entity/relation extraction and malware analysis language understanding. Need to verify dataset access, license, and annotation format before use. |
| MOTIF | academic dataset | malware family labels, aliases, report mapping | `sft-candidate`, `evaluation-candidate`, `rag-candidate` | Metadata and mapping fixture only after license review | Strong candidate for family-name normalization, alias handling, and report-grounded evaluation. Avoid treating family labels as final truth without provenance. |
| EMBER / EMBER2024 | GitHub, paper, benchmark dataset | PE static features, metadata, labels, feature vectors | `benchmark-candidate`, `metadata-evaluation`, `hold` | Do not commit dataset dump; external artifact only | Good benchmark direction for malware detection metadata and feature-vector evaluation. Not a first SFT source for AegisLM text generation. |
| SOREL-20M | GitHub, public S3, paper | large PE metadata/features, labels, disarmed binaries | `benchmark-candidate`, `metadata-evaluation`, `hold` | Do not commit dataset dump or binaries; external artifact only | Very large dataset. Only specific metadata or small derived safe fixtures should be considered. Raw/disarmed binaries remain out of Git and out of v0 scope. |
| Binary-30K | Hugging Face dataset | binary metadata, labels, tokenized binary representation, splits | `benchmark-candidate`, `metadata-evaluation`, `hold` | Do not commit dataset dump; inspect files before use | Potentially convenient benchmark because it exposes metadata and splits. Must audit dataset card, files, and loading path before use. |

## 5. Candidate Details

### APTNotes

- URL: `https://github.com/aptnotes/data`
- Primary fit: CTI summarization, APT/campaign context, evidence extraction, ATT&CK mapping examples
- Initial AegisLM role: SFT/RAG/evaluation candidate
- Raw malware risk: low, but linked reports may contain technical malware details
- Safety decision: use report metadata and selected excerpts only after source/license review

APTNotes should be treated as a report index, not as a ready-to-train dataset. The useful unit is likely one report section or one curated summary record with source provenance.

### MalwareTextDB

- URL: `https://aclanthology.org/P17-1148/`
- Primary fit: annotated malware-analysis language
- Initial AegisLM role: SFT/evaluation candidate
- Raw malware risk: low if dataset contains text only
- Safety decision: verify license and annotation files before any conversion

MalwareTextDB is attractive because it is closer to natural language malware analysis than PE feature datasets. It should be checked for field shape, annotation labels, and redistribution terms.

### MOTIF

- URL: `https://arxiv.org/abs/2111.15031`
- Primary fit: malware family labels, aliases, report-grounded references
- Initial AegisLM role: SFT/RAG/evaluation candidate
- Raw malware risk: medium if sample references are included; use metadata/report mappings only
- Safety decision: avoid binary sample handling; focus on alias and report mapping metadata

MOTIF is useful for evaluating whether AegisLM can avoid hallucinated family names and preserve uncertainty when evidence is incomplete.

### EMBER / EMBER2024

- EMBER URL: `https://github.com/elastic/ember`
- EMBER2024 paper: `https://arxiv.org/abs/2506.05074`
- Primary fit: malware detection benchmark, PE static feature evaluation
- Initial AegisLM role: benchmark/metadata evaluation candidate
- Raw malware risk: medium; dataset focuses on features and metadata, but related tooling can process PE files
- Safety decision: no raw PE files or dataset dumps in Git

EMBER-style data is better for benchmark and metadata evaluation than direct instruction tuning. AegisLM can use derived metadata summaries or evaluation labels, but should not claim malware-detection benchmark performance without a reproducible experiment log.

### SOREL-20M

- URL: `https://github.com/sophos/SOREL-20M`
- Primary fit: large-scale PE detection benchmark
- Initial AegisLM role: benchmark/metadata evaluation candidate
- Raw malware risk: high because the dataset includes very large binary-related artifacts
- Safety decision: hold until storage, terms, and artifact handling are explicitly planned

SOREL-20M is too large for immediate Phase D/E use. If used later, the first step should be a metadata-only review and a tiny derived fixture outside the raw dataset.

### Binary-30K

- URL: `https://huggingface.co/datasets/mjbommar/binary-30k`
- Primary fit: compact benchmark-style binary metadata and tokenized representation
- Initial AegisLM role: benchmark/metadata evaluation candidate
- Raw malware risk: medium; Hugging Face repositories must be audited before loading
- Safety decision: inspect dataset files and avoid executing remote loading code

Binary-30K may be useful as a compact benchmark candidate, but it should go through supply-chain review before use. Prefer metadata and labels first, not tokenized binary content for SFT.

## 6. Phase D/E Recommendation

For Phase D/E, prioritize candidates in this order:

1. APTNotes for CTI report metadata and RAG/evidence workflows.
2. MalwareTextDB for malware-analysis language and annotation-driven evaluation.
3. MOTIF for family alias/report mapping and hallucination checks.
4. EMBER or Binary-30K for metadata-based benchmark exploration.
5. SOREL-20M only after storage, legal, and safety handling are explicitly planned.

Phase E tiny SFT should start with text/metadata records, not raw binary datasets. Benchmark datasets should be used to define evaluation context or metadata-grounded prompts unless a separate ML benchmark experiment is opened.

## 7. Open Questions

- Which license terms allow derived training examples?
- Which candidates can produce metadata-only fixtures that are safe to commit?
- Which candidates should be kept entirely outside Git as external artifacts?
- How should dataset provenance be represented in `aegislm/schemas.py` records?
- Which candidates belong to held-out evaluation only and must never enter training data?

## 8. Related Work

- Linear: THE-62
- `docs/DATA_STRATEGY.md`
- `docs/EVALUATION_PLAN.md`
- `docs/FINETUNING_EXPERIMENT_PLAN.md`

<a id="2026-10-10-vulnerable-project-candidates"></a>

## 9. 2026-10-10: 실제 취약점이 포함된 C/C++ 프로젝트 평가 자료

이번 조사 목적은 알려진 취약점이 포함된 프로젝트 전체를 모델에게 제공하고,
위치와 원인을 찾아내는지 평가할 자료를 확보하는 것이다. 함수별 라벨 데이터에서
프로젝트 단위 탐색·판단으로 확장하려는 논의이며, 신규 학습 데이터 채택 결정은 아니다.
정적/동적 분석은 분석 방법의 구분이고, 취약한 프로젝트를 사용한다는 것은 입력
데이터의 성격이다. 소스를 정적으로 분석하더라도 실제 취약점 발견 여부를 평가할 수 있다.

아래는 공식 문서에서 확인한 제공 내용이다. 이번 조사에서 새로운 데이터나 이미지를
다운로드하거나 빌드·실행하지 않았으며, 현재 서버의 재현 가능성과 사례별 라이선스는
아직 검증하지 않았다. 앞 절의 CTI/PE 후보 우선순위와 별개인 C/C++ 평가 후보군이다.

| 후보·출처 | 제공 내용 | 이번 목적의 적용 | 확인할 한계 |
| --- | --- | --- | --- |
| [ARVO](https://github.com/n132/ARVO), [ARVO-Meta](https://github.com/n132/ARVO-Meta) | 실제 취약점별 취약·수정 소스와 빌드·재현 환경, 패치·재현 입력·예상 오류 기록 | 역사적 취약 버전의 프로젝트를 평가할 첫 검토 후보 | 자동 식별한 패치가 정답임을 보장하지 않음. 사례별 재현·패치 검수 필요 |
| [Magma](https://hexhive.epfl.ch/magma/), [저장소](https://github.com/HexHive/magma) | libpng·libtiff·libxml2·Poppler 등 실제 프로젝트에 과거 버그를 이식하고 도달·발현 관측 코드를 추가한 벤치마크 | 알려진 버그가 포함된 프로젝트의 탐색 평가 후보 | 역사적 원본 버전과 구분. 버그 ID·관측 코드가 모델에 정답을 노출할 수 있음 |
| [OSS-Fuzz 공개 취약점 기록](https://github.com/google/oss-fuzz-vulns), [빌드 인프라](https://github.com/google/oss-fuzz) | 공개된 취약점과 영향받는 커밋 정보, 프로젝트별 빌드·퍼징 구성 | 프로젝트와 버전 후보를 넓히는 근거 | 메타데이터만으로 해당 버전의 전체 프로젝트·빌드 환경·정답이 자동 확보되는 것은 아님 |

세 후보 모두 `evaluation-candidate`, `benchmark-candidate`로 기록한다.
취약한 일반 소프트웨어와 악성코드 샘플은 구분하며, 재현 입력·바이너리·원본 소스
덤프·이미지는 Git 밖에 둔다. 프로젝트별 라이선스와 재배포 조건도 별도로 확인한다.

### ARVO를 실제로 받는 위치와 단위

1. [ARVO-Meta Releases](https://github.com/n132/ARVO-Meta/releases)에서 `arvo.db`를 확보한다.
2. DB의 사례별 레코드에서 이미지 참조, 수정 정보, 재현 입력과 예상 오류 정보를 확인한다.
3. 해당 사례의 이미지에서 취약 버전 또는 수정 버전의 프로젝트 소스·환경을 확보한다.

`arvo.db`는 사례 목록과 연결 정보다. 프로젝트 원본 전체가 DB에 들어 있다고
가정하지 않는다. 공식 안내는 각 레코드에 관련 이미지와 사용 명령을 제공한다고
설명한다. 실제 이미지 저장소는 [Docker Hub n132/arvo](https://hub.docker.com/r/n132/arvo)다.
선택할 릴리스·사례 ID·이미지 digest·소스 commit·빌드 조건은 도입 시 고정한다.
[공식 데이터 구성 및 사용 안내](https://github.com/n132/ARVO-Meta#tldr).

**기존 로컬 이력:** ARVO는 처음 발견한 후보가 아니다.
[데이터셋 이력](DATASET_ARTIFACT_INVENTORY.md)에 따르면 기존 200건 패치 검수 계획은
11건 검수 중 11건 오류로 오류 예산 10을 넘어 조기 중단했고, 189건은 미완료다.
이것을 전체 ARVO 부적합이나 200건 검수 완료로 해석하지 않는다. 원 실패 사유와
현재 선택할 사례를 대조한 뒤, 실제 재현·수정 대응을 확인한 사례만 정답 후보로 삼는다.

### 후속 평가와 바이너리 경로

모델에는 프로젝트 소스를 주고, 평가자는 취약점 정보·패치·재현 근거를 별도로
보유한다. 수정 버전은 특정 취약점이 제거된 비교 대상이며 프로젝트 전체의
무취약성을 보장하는 음성 라벨이 아니다. 상세 제안은
[프로젝트 평가 논의](EVALUATION_PLAN.md#2026-10-10-project-evaluation-proposal)에 기록한다.

실행 파일 평가는 후속 후보로 남긴다. [Ghidra](https://github.com/NationalSecurityAgency/ghidra)는
디스어셈블·디컴파일 기능을 제공하므로, 동일 소스에서 직접 빌드한 바이너리의
디컴파일 결과와 원본 소스 판단을 비교할 수 있다. 이는 현재 모델이 바이너리를
직접 이해한다고 검증한 결과가 아니다. 정적 추출에는 대상 실행 파일을 실행할
필요가 없으며, 취약점 재현을 위한 실행 검증과 구분한다. 도구 설치·실행은 하지 않았다.
