# 기존 데이터셋 폴더와 정리 이력

관찰일: **2026-09-29**. 로컬 `data/processed`의 **83개 폴더**, 파일 크기 합계
**55.54 GiB**를 기록했다. 시도와 실패 원인을 남긴 뒤 학습 전에 정리하기 위한 목록이다.
2026-09-29 목록화 시점에는 삭제·이동·재학습하지 않았다.
아래 83개 표는 그 시점의 스냅샷이며, 이후 정리 결과는 다음 절에 추가한다.

현재 새 학습·평가에 선택한 경로는 `cc-source-candidates-20260928-v5`다.
10,000/1,000/500은 train/validation/test이며 원천 라벨 기반 판단 후보다.
근거 줄 검수는 별도 작업이고 `approved_for_training=false`가 유지된다.
이전 실험 폴더를 여기에 합치지 않는다. 상세 계약과 v1–v5 수정 이력은
[데이터 전략](DATA_STRATEGY.md)의 C/C++ 재구성 및 학습 전 정리 절을 따른다.

## 2026-10-02 정리 완료 — 현재 상태

1단계 범위의 정리를 완료했다. `cc-source-candidates-20260928-v1`의 9개 파일은
`data/cache/cc-source-normalized-20260928`로 이관했다. v2/v3/v4 데이터 폴더와
v3/v4 검사 폴더는 기록 보존·재현 검증 후 삭제했다. 삭제된 기존 중간 파일 크기는
121.56 MiB이며, 2.39 GiB의 풀/인덱스는 보존했다.

새 위치에서 v5의 데이터/검사 11개 파일이 바이트 단위로 재현됐고,
최종 v5의 정리 전/후 파일 해시 및 10,000/1,000/500 export 검사가 통과했다.
`data/processed`는 현재 79개 폴더이며 새 C/C++ 후보는 v5 하나다.
기존 source 제외 입력·CVEfixes DB 등 다른 계열은 이번 삭제 대상에 포함하지 않았다.

현재 재생성 명령은 [데이터 전략](DATA_STRATEGY.md)에 있다.
원래 목록의 v1/v4 경로는 역사적 입력 경로이며, 새 캐시와 history 사본으로 대응한다.
최종 frozen manifest의 옛 경로·해시는 덮어쓰지 않았다.
완료 내역/원래 경로/새 경로/보존 해시는
`outputs/cc-source-cleanup-20261002/cleanup-manifest.json`에 기록했다.
학습 설정 연결은 다음 단계이며 아직 새 학습을 실행하지 않았다.

## 기록 위치와 확인 범위

- 이 문서: Git에 남길 폴더명, 목적, 주요 결과, 계보, 정리 조건.
- `outputs/legacy-dataset-inventory-20260929/inventory.json`: 모든 폴더의 파일명·크기,
  metadata 요약, 코드/설정 참조 위치, 관련 outputs/adapters/checkpoints 목록.
- 같은 경로의 `metadata/`: 폴더 최상위 JSON/Markdown/log 및 SHA256SUMS 중
  8 MiB 이하 파일과 Q1R10/Q1R11 감사·최근 품질/준비 감사 사본, 합계 **238개**.
- 같은 경로의 `inventory.py`, `SHA256SUMS`: 목록 작성 방법과 보존 사본의 해시.
- `outputs/cc-source-candidates-history-20260929`: 앞서 보존한 새 C/C++ v1–v5 시도 이력.

`outputs`는 Git 제외 경로다. 정리 시 사본도 별도 저장소에 함께 보관해야 한다.
이 문서만으로 원본을 재생성할 수는 없다. metadata에 검수 자료가 포함될 수 있으므로
원문을 Git 문서에 옮기지 않는다. 모든 하위 검수 파일을 복사한 archive는 아니다.

용량은 파일의 논리 크기 합계다. 디렉터리 블록 제외, hardlink 중복 계산, 반올림 때문에
실제 회수 공간과 다를 수 있다. `0.0 MiB`는 빈 폴더라는 뜻이 아니다.
원천 JSONL·Parquet·DB·모델 가중치를 복사하거나 전수 재검증하지 않았다.
기존 SHA256SUMS를 보존한 사실과 데이터 전체 무결성 검증은 구분한다.

표의 상태는 **당시 metadata의 선언**이다. 자동 검사 통과, 수동 근거 검수,
학습 완료, 모델 품질 통과는 별개다. 상태 없는 폴더의 성공/실패를 이름으로 추정하지 않는다.
여러 상태는 기록의 병존이며 시간순 판정이 아니다. 코드 참조 조사는 현재 저장소의
`aegislm/scripts/configs/tests` 문자열 및 source glob 의존성 기준이다.
외부 B200 저장소나 모든 동적 경로에 참조가 없다는 보장은 아니다.

## 계열별 시도와 교훈

| 계열 | 확인한 목적·결과 | 재사용/정리 시 주의 |
| --- | --- | --- |
| `hf-full-v1` | 초기 HF 통합 export. manifest에 BigVul 150,908, DiverseVul 264,392, cybersecurity QA 709건 변환 기록 | 현재 C/C++ 판단 후보와 형식·선별 기준이 다름 |
| `phase-f-source-v2*` | catalog와 eligible/quarantine/reject/reserve 구성 개정. train 10,000/validation 1,000/challenge 500 기록 | 이후 SARD 기반 source-v3 계보와 구분 |
| `phase-f-sard-grounded-*` | 근거 target, rubric, remediation, 길이 축약 반복. v1 수동 품질 실패, v2 통합 준비. candidate에는 검수 대기/자동 실패 공존 | 최신 번호만으로 최종 채택 판단 금지 |
| `phase-f-source-v3/v4/v5/v5-r1` | SARD 근거 자료를 source contract로 export. 당시 학습 승인 기록 | 현재 선택 자료가 아님. 기존 설정과 중복 제외 규칙에 연결됨 |
| `phase-f-source-multitask/compact/decision/evidence-lines*` | 보고·판단 분리 및 짧은 근거 출력 실험 | canary/diagnostic 승인과 독립 평가 품질은 다름 |
| `phase-f-source-*blind*` | 기존 480건과 추가 fresh500. fresh500은 실제 학습 계보와 중복 발견 | blind/frozen 이름과 자동 검사 통과만으로 미노출 평가라 판단 금지 |
| `phase-f-binary-derived-*` | 최초 v1 binary canary 승인. r2, target-v2/v3/v4/v5/v9는 수동 target 품질 실패, v7은 검수 필요 기록 | 자동 token/형식 검사 통과가 근거 타당성을 보장하지 않음 |
| `phase-f-binary-*supply*`, b0/f7 | binary 후보·정렬·관계/target/tokenizer 공급 탐색 | export와 공급 후보를 구분; 상태 없는 항목의 성능은 미확인 |
| ARVO | metadata feasibility 후 patch 검수. 200건 계획에서 11건 검수 중 11건 오류로 예산 10 초과, 조기 실패; 189건 미완료 | 200건 전수 검수 완료로 기록하면 안 됨 |
| Assemblage/BinKit/DecompileBench | Assemblage strict complete 0/249,121. BinKit 사전 결정 필요. DecompileBench alignment reference only | 정렬 참고 자료를 검증된 취약점 SFT 정답으로 취급하지 않음 |
| CVEfixes | archive 검사 → 방어적 import → 공급 표현 수정 이력. 학습 승인 false | DB는 현재 builder 입력이므로 구버전 폴더로 일괄 삭제 금지 |
| EMBER ELF | feature materialization, LightGBM baseline 및 공식 모델 평가. materialized train 26,000/test 6,000 기록 | C/C++ 함수 SFT와 다른 benchmark. test 고유 파일 해시 5,989 기록도 보존 |
| `cc-source-candidates-20260928-v1..v5` | 분할 공급 부족 → 공급 보완 → tokenizer별 길이 초과 수정. v5 형식·분할·길이 검사 통과 | 근거 검수 완료/모델 품질 통과를 뜻하지 않음 |

상위 source manifest에 기록된 구체 계보:

```text
phase-f-sard-grounded-v2 → phase-f-source-v3
phase-f-sard-grounded-v3-remediation → phase-f-source-v4
phase-f-sard-grounded-v4-compact [manifest profile] → phase-f-source-v5
phase-f-sard-grounded-v4-compact-candidate3 → phase-f-source-v5-r1
```

`phase-f-sard-grounded-v4-compact`라는 독립 폴더는 이번 목록에 없다.
manifest profile과 실제 존재하는 폴더를 같은 것으로 간주하지 않는다.

### Q1R10·Q1R11과 평가 누출

```text
phase-f-source-v5-r1
├─ phase-f-source-decision-v1 → Q1R10
└─ phase-f-source-multitask-v1 (report)
   └─ phase-f-source-compact-v1
      └─ phase-f-source-evidence-lines-v1 → Q1R11
```

실제 LLaMA-Factory 입력은 최종 두 폴더의 `llamafactory/train.jsonl` 및
`llamafactory/validation.jsonl`이다. Q1R10은 10,000/1,000건,
Q1R11은 길이 격리 후 9,975/996건이다. `candidate-2`를 실제 사용 경로로 단정하지 않는다.

2026-09-28 감사에서 fresh500은 두 실험 각각의 train 코드 206건,
validation 코드 292건과 겹쳤다. 제외 기준은 이전 `phase-f-sard-grounded-v2`였고
실제 학습 계보 `source-v5-r1`과 달랐다. fresh500 결과를 독립 미노출 평가로 사용하지 않는다.
원래 challenge500 및 untouched480에는 같은 train/validation 코드 중복이 없었으므로
모든 과거 평가를 일괄 무효라고 기록하지 않는다. 학습 풀 포함과 optimizer 실제 노출도 구분한다.

근거는 `outputs/q1r10-q1r11-dataset-audit-20260928/{summary.md,report.json,audit.py}`이며
이번 archive에 사본을 보존했다. 이후 중복 제외는 실제 사용한 데이터 계보를 기준으로 한다.

## 삭제 전에 해소할 의존성

| 경로/규칙 | 확인된 연결 | 정리 전 조건 |
| --- | --- | --- |
| `cc-source-candidates-20260928-v1/pool` 및 index | v5 생성에 사용한 공용 정규화 풀 | 이관 시 해시·경로 대응표 보존 및 재생성 검증 |
| `outputs/cc-source-candidates-20260928-v4/exclude-overlength-ids.json` | v5 생성 명령 입력; history에 사본 있음 | 새 재현 명령이 보존 사본을 읽는지 확인 |
| `phase-f-cvefixes-v1.0.8/CVEfixes.db`, `import-report.json` | `scripts/build_cc_source_corpus.py`의 원천 입력 | 약 48.14 GiB 폴더 보존/이관 및 경로 재연결 |
| `phase-f-source-*` | builder의 `historical_fingerprints()`가 glob 후 지정 train/validation/challenge 파일을 읽음 | 제외 fingerprint·입력 해시 동결 후 원본 폴더 없이 동일 제외 결과 검증. glob에 걸리는 모든 폴더가 실제 코드 입력을 제공하지는 않음 |
| `phase-f-source-v5-r1` | `configs/source_v2_*.json`, PEFT 스크립트, two-stage 준비 스크립트의 기존 참조 | 기존 실행 config 보존. 새 설정 전환 후 참조 재검사 |
| decision/evidence/fresh-blind 네 폴더 | `aegislm/training/two_stage.py`의 동결 경로 | 새 데이터 계약/평가 경로 연결 전 기존 준비 명령과 혼동 방지 |

용량 대부분은 CVEfixes DB다. 새 v5 약 60.6 MiB와 v1 공용 풀 등을 포함한
폴더 약 2.39 GiB를 구분한다. 단순히 폴더 수가 많다는 이유로 모두 삭제하지 않는다.

## 관련 학습·평가 산출물

이번 archive를 제외한 `outputs`의 기존 폴더도 inventory에 파일 수와 용량을 기록했다.

- `cc-source-candidates-20260928-v3`, `-v4`, `-v5`: export/token 검사·제외 목록.
- `cc-source-candidates-history-20260929`: 새 데이터 버전별 실패·수정 및 재현 자료.
- `q1r10-q1r11-dataset-audit-20260928`: 실제 학습 경로와 fresh500 누출 감사.
- `source-two-stage-20260928-v1`: 준비 단계 감사. 폴더 존재를 새 학습 완료로 읽지 않음.
- `source-v2-unsloth-full-comparison-20260927-v1`: 학습 및 후속 품질 감사.
- `source-v2`, `the-58`, `the-73`: 기존 실행 자료. 이번 목록화에서 실행 품질을 재판정하지 않음.

`adapters/`와 `checkpoints/` 양쪽에 다음 일곱 이름이 있다:
`source-v2-peft-control`, `source-v2-peft-cwe-balanced`, `source-v2-qlora`,
`source-v2-unsloth-fresh-v1`, `source-v2-unsloth-full-comparison-20260927-v1`,
`source-v2-unsloth-v2`, `tiny-sft-poc`.
폴더 존재만으로 가중치 저장 또는 학습 성공을 주장하지 않는다. 가중치 삭제 대상은 확정하지 않았다.

## 정리 실행 순서

1. 문서, metadata 사본, 감사/실패 보고서, 재현 코드와 config를 보존한다.
2. 계보와 SHA 목록을 고정한다. 없는 과거 코드·명령은 복원했다고 주장하지 않는다.
3. 의존성을 이관하거나 동결된 대체 입력으로 연결하고 재생성/중복 제외를 검증한다.
4. 실제 삭제할 폴더와 회수 예상 용량을 별도 cleanup manifest에 확정한다.
   아래 **정리 후보는 삭제 완료나 삭제 명령 목록이 아니다**.
5. 학습 전에 확정된 중간 산출물을 정리하고 시각·이전/이후 경로·보존 해시·결과를 기록한다.
6. 최종 v5의 파일/분할/길이 검사와 새 학습 config 경로를 확인한다.

`data/raw_data`, 모델 캐시, adapter/checkpoint, 독립 benchmark 원본의 일괄 삭제로
범위를 넓히지 않는다. 과거 승인·실패 metadata는 덮어쓰지 않고 이후 결정을 추가한다.

## 전체 폴더 목록

접두사는 모두 `data/processed/`다. 상태는 최상위 metadata에서 추출한 대표 표기이며
전체 기록은 archive에 있다. “정리 후보”도 외부 참조와 재현 자료 확인 후 확정한다.
생성 명령/seed/상위 artifact는 존재하는 metadata 범위에서 보존했다.

| 실제 폴더명 | 파일 용량 (MiB) | 용도 | 당시 기록의 상태 | 정리 판단 |
| --- | ---: | --- | --- | --- |
| `cc-source-candidates-20260928-v1` | 2448.7 | C/C++ 신규 판단 후보 재구성 | 상태 표기 없음; 상세 inventory 참조 | 보존/이관: 공용 pool·index |
| `cc-source-candidates-20260928-v2` | 0.0 | C/C++ 신규 판단 후보 재구성 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `cc-source-candidates-20260928-v3` | 60.9 | C/C++ 신규 판단 후보 재구성 | source_label_and_cwe_review_required | 근거 보존 후 정리 후보 |
| `cc-source-candidates-20260928-v4` | 60.7 | C/C++ 신규 판단 후보 재구성 | source_label_and_cwe_review_required | 근거 보존 후 정리 후보 |
| `cc-source-candidates-20260928-v5` | 60.6 | C/C++ 신규 판단 후보 재구성 | source_label_and_cwe_review_required | 보존: 현재 선택 후보 |
| `hf-full-v1` | 1069.8 | 초기 HF 전체 자료 export | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-arvo-buffer-feasibility-v1` | 0.1 | ARVO metadata/patch 근거 후보 검수 | manual_feasibility_ready | 근거 보존 후 정리 후보 |
| `phase-f-arvo-patch-review-v1` | 1.3 | ARVO metadata/patch 근거 후보 검수 | manual_review:fail_early | 근거 보존 후 정리 후보 |
| `phase-f-arvo-patch-review-v1-pilot` | 0.0 | ARVO metadata/patch 근거 후보 검수 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-assemblage-linuxelf-metadata-v1` | 0.0 | Assemblage 정렬·출처 metadata 검사 | compressed_artifact_verified; metadata_quality_fail; single_alignment_candidate_ready | 근거 보존 후 정리 후보 |
| `phase-f-binary-alignment-supply-preflight-v1` | 0.0 | binary 후보 공급·정렬·target 사전 검사 | single_alignment_candidate_ready | 근거 보존 후 정리 후보 |
| `phase-f-binary-b0-v1` | 1.8 | binary 후보 공급·정렬·target 사전 검사 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-binary-derived-v1` | 56.8 | binary target export·검수 개정 | approved_for_binary_canary | 근거 보존 후 정리 후보 |
| `phase-f-binary-derived-v1-r2` | 56.6 | binary target export·검수 개정 | manual_target_quality_gate_failed | 근거 보존 후 정리 후보 |
| `phase-f-binary-derived-v1-target-v2-r1` | 56.5 | binary target export·검수 개정 | manual_target_quality_gate_failed | 근거 보존 후 정리 후보 |
| `phase-f-binary-derived-v1-target-v3-r1` | 56.4 | binary target export·검수 개정 | manual_target_quality_gate_failed | 근거 보존 후 정리 후보 |
| `phase-f-binary-derived-v1-target-v4-r1` | 56.4 | binary target export·검수 개정 | manual_target_quality_gate_failed | 근거 보존 후 정리 후보 |
| `phase-f-binary-derived-v1-target-v5-r2` | 57.2 | binary target export·검수 개정 | manual_target_quality_gate_failed | 근거 보존 후 정리 후보 |
| `phase-f-binary-derived-v1-target-v7-r1` | 57.2 | binary target export·검수 개정 | manual_target_review_required | 근거 보존 후 정리 후보 |
| `phase-f-binary-derived-v1-target-v9-r1` | 56.9 | binary target export·검수 개정 | manual_target_quality_gate_failed | 근거 보존 후 정리 후보 |
| `phase-f-binary-f7-v1` | 96.9 | binary 후보 공급·정렬·target 사전 검사 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-binary-relation-supply-v1` | 71.8 | binary 후보 공급·정렬·target 사전 검사 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-binary-relation-supply-v3` | 74.1 | binary 후보 공급·정렬·target 사전 검사 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-binary-relation-supply-v4` | 11.7 | binary 후보 공급·정렬·target 사전 검사 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-binary-relation-supply-v5` | 79.3 | binary 후보 공급·정렬·target 사전 검사 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-binary-relation-supply-v6` | 5.9 | binary 후보 공급·정렬·target 사전 검사 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-binary-relation-supply-v7` | 1.1 | binary 후보 공급·정렬·target 사전 검사 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-binary-relation-supply-v8` | 4.2 | binary 후보 공급·정렬·target 사전 검사 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-binary-target-v2-supply-v1` | 58.1 | binary 후보 공급·정렬·target 사전 검사 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-binary-target-v3-supply-v1` | 58.1 | binary 후보 공급·정렬·target 사전 검사 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-binary-target-v4-supply-v1` | 58.1 | binary 후보 공급·정렬·target 사전 검사 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-binary-target-v5-supply-v1` | 53.3 | binary 후보 공급·정렬·target 사전 검사 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-binary-target-v7-supply-v1` | 49.9 | binary 후보 공급·정렬·target 사전 검사 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-binary-target-v9-supply-v1` | 49.7 | binary 후보 공급·정렬·target 사전 검사 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-binary-tokenizer-supply-v1` | 55.9 | binary 후보 공급·정렬·target 사전 검사 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-binkit-v2-metadata-preflight-v1` | 0.0 | BinKit 정렬 metadata 사전 검사 | alignment_preflight_requires_decision | 근거 보존 후 정리 후보 |
| `phase-f-cvefixes-archive-inventory-v1` | 0.0 | CVEfixes archive/import·label 공급 검사 | assembly_pass; gzip_stream_pass; inventory_pass | 근거 보존 후 정리 후보 |
| `phase-f-cvefixes-v1.0.8` | 49298.1 | CVEfixes archive/import·label 공급 검사 | defensive_import_pass; supply_inventory_fail; supply_inventory_pass | 보존/이관: builder 입력 DB |
| `phase-f-decompile-bench-shard-00000-inventory-v1` | 1.1 | DecompileBench 정렬·출처 검수 | selective_alignment_review_ready; alignment_reference_only; manual_alignment_review_ready | 근거 보존 후 정리 후보 |
| `phase-f-ember2024-elf-lgbm-baseline-v1` | 5.4 | EMBER ELF feature benchmark 계열 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-ember2024-elf-official-model-evaluation-v1` | 1.8 | EMBER ELF feature benchmark 계열 | 상태 표기 없음; 상세 inventory 참조 | 근거 보존 후 정리 후보 |
| `phase-f-ember2024-elf-test-materialized-v1` | 18.9 | EMBER ELF feature benchmark 계열 | materialization_pass | 근거 보존 후 정리 후보 |
| `phase-f-ember2024-elf-test-materialized-v2` | 19.0 | EMBER ELF feature benchmark 계열 | materialization_pass | 근거 보존 후 정리 후보 |
| `phase-f-ember2024-elf-test-materialized-v3` | 19.0 | EMBER ELF feature benchmark 계열 | materialization_pass | 근거 보존 후 정리 후보 |
| `phase-f-ember2024-elf-test-v1` | 18.9 | EMBER ELF feature benchmark 계열 | inventory_pass; benchmark_metadata_pass; materialization_pass | 근거 보존 후 정리 후보 |
| `phase-f-ember2024-elf-train-materialized-v1` | 79.5 | EMBER ELF feature benchmark 계열 | materialization_pass | 근거 보존 후 정리 후보 |
| `phase-f-ember2024-elf-train-materialized-v2` | 79.9 | EMBER ELF feature benchmark 계열 | materialization_pass | 근거 보존 후 정리 후보 |
| `phase-f-ember2024-elf-train-materialized-v3` | 79.9 | EMBER ELF feature benchmark 계열 | materialization_pass | 근거 보존 후 정리 후보 |
| `phase-f-ember2024-elf-train-v1` | 0.0 | EMBER ELF feature benchmark 계열 | inventory_pass; benchmark_metadata_pass | 근거 보존 후 정리 후보 |
| `phase-f-patch-label-supply-preflight-v1` | 0.0 | patch label 공급 후보 사전 검사 | acquisition_candidate_ready | 근거 보존 후 정리 후보 |
| `phase-f-sard-grounded-v1` | 47.0 | SARD/Juliet 근거 target 구성·검수 | manual_quality_gate_failed | 근거 보존 후 정리 후보 |
| `phase-f-sard-grounded-v2` | 59.0 | SARD/Juliet 근거 target 구성·검수 | ready_for_source_v3_integration | 근거 보존 후 정리 후보 |
| `phase-f-sard-grounded-v2-candidate` | 57.9 | SARD/Juliet 근거 target 구성·검수 | manual_review_required | 근거 보존 후 정리 후보 |
| `phase-f-sard-grounded-v2-candidate2` | 57.8 | SARD/Juliet 근거 target 구성·검수 | manual_review_required | 근거 보존 후 정리 후보 |
| `phase-f-sard-grounded-v2-candidate3` | 57.8 | SARD/Juliet 근거 target 구성·검수 | manual_review_required | 근거 보존 후 정리 후보 |
| `phase-f-sard-grounded-v2-candidate4` | 57.6 | SARD/Juliet 근거 target 구성·검수 | manual_review_required | 근거 보존 후 정리 후보 |
| `phase-f-sard-grounded-v2-candidate5` | 58.4 | SARD/Juliet 근거 target 구성·검수 | manual_review_required | 근거 보존 후 정리 후보 |
| `phase-f-sard-grounded-v2-candidate6` | 58.5 | SARD/Juliet 근거 target 구성·검수 | manual_review_required | 근거 보존 후 정리 후보 |
| `phase-f-sard-grounded-v2-candidate7` | 58.7 | SARD/Juliet 근거 target 구성·검수 | manual_review_required | 근거 보존 후 정리 후보 |
| `phase-f-sard-grounded-v2-candidate8` | 58.7 | SARD/Juliet 근거 target 구성·검수 | manual_review_required | 근거 보존 후 정리 후보 |
| `phase-f-sard-grounded-v2-pre-rubric` | 57.4 | SARD/Juliet 근거 target 구성·검수 | manual_review_required | 근거 보존 후 정리 후보 |
| `phase-f-sard-grounded-v3-remediation` | 59.6 | SARD/Juliet 근거 target 구성·검수 | ready_for_source_v3_integration | 근거 보존 후 정리 후보 |
| `phase-f-sard-grounded-v4-compact-candidate` | 55.5 | SARD/Juliet 근거 target 구성·검수 | automated_quality_gate_failed | 근거 보존 후 정리 후보 |
| `phase-f-sard-grounded-v4-compact-candidate2` | 55.6 | SARD/Juliet 근거 target 구성·검수 | ready_for_source_v3_integration | 근거 보존 후 정리 후보 |
| `phase-f-sard-grounded-v4-compact-candidate3` | 55.6 | SARD/Juliet 근거 target 구성·검수 | ready_for_source_v3_integration | 근거 보존 후 정리 후보 |
| `phase-f-sard-grounded-v4-compact-candidate4` | 55.5 | SARD/Juliet 근거 target 구성·검수 | manual_review_required | 근거 보존 후 정리 후보 |
| `phase-f-source-compact-v1` | 43.3 | 짧은 report target 변환 | approved_for_compact_canary | 보류: 과거 계보·제외 규칙 |
| `phase-f-source-compact-v1-candidate-2` | 43.3 | 짧은 report target 변환 | approved_for_compact_canary | 보류: 과거 계보·제외 규칙 |
| `phase-f-source-decision-v1` | 37.7 | Q1R10 판단 전용 export | approved_for_diagnostic_training | 보류: 과거 계보·제외 규칙 |
| `phase-f-source-evidence-lines-v1` | 45.0 | Q1R11 근거 줄 export 계열 | approved_for_evidence_canary | 보류: 과거 계보·제외 규칙 |
| `phase-f-source-evidence-lines-v1-candidate-2` | 45.0 | Q1R11 근거 줄 export 계열 | approved_for_evidence_canary | 보류: 과거 계보·제외 규칙 |
| `phase-f-source-fresh-blind-500-v1` | 3.8 | 추가 blind 평가; 실제 계보와 중복 발견 | frozen_blind | 보류: 과거 계보·제외 규칙 |
| `phase-f-source-fresh-blind-contracts-500-v1` | 1.0 | 추가 blind 평가; 실제 계보와 중복 발견 | frozen_blind | 보류: 과거 계보·제외 규칙 |
| `phase-f-source-multitask-v1` | 114.0 | 판단/report 혼합 canary | approved_for_multitask_canary | 보류: 과거 계보·제외 규칙 |
| `phase-f-source-multitask-v1-candidate2` | 114.0 | 판단/report 혼합 canary | approved_for_multitask_canary | 보류: 과거 계보·제외 규칙 |
| `phase-f-source-untouched-blind-480-v1` | 1.3 | 기존 challenge 중 미노출 480건 | 상태 표기 없음; 상세 inventory 참조 | 보류: 과거 계보·제외 규칙 |
| `phase-f-source-v2` | 151.6 | source 학습·평가 구성 개정 | 상태 표기 없음; 상세 inventory 참조 | 보류: 과거 계보·제외 규칙 |
| `phase-f-source-v2-r1` | 233.6 | source 학습·평가 구성 개정 | 상태 표기 없음; 상세 inventory 참조 | 보류: 과거 계보·제외 규칙 |
| `phase-f-source-v2-r2` | 241.2 | source 학습·평가 구성 개정 | 상태 표기 없음; 상세 inventory 참조 | 보류: 과거 계보·제외 규칙 |
| `phase-f-source-v3` | 97.5 | source 학습·평가 구성 개정 | approved_for_training | 보류: 과거 계보·제외 규칙 |
| `phase-f-source-v4` | 98.9 | source 학습·평가 구성 개정 | approved_for_training | 보류: 과거 계보·제외 규칙 |
| `phase-f-source-v5` | 91.2 | source 학습·평가 구성 개정 | approved_for_training | 보류: 과거 계보·제외 규칙 |
| `phase-f-source-v5-r1` | 91.2 | source 학습·평가 구성 개정 | approved_for_training | 보류: 과거 계보·제외 규칙 |
