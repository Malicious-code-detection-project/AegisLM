# B200 실험 보고서 — GPT-OSS-20B 결과와 5개 모델 비교 준비

2026-10-14 후속 결과: [후보 7건의 정적 분석·호출 문맥 검토](FINETUNING_EXPERIMENT_PLAN.md#2026-10-14-context-evidence-results).
Cppcheck 실행과 문맥 검토를 완료했다. 확장 범위에서 ROSE·Kerberos 2건의 잠정 양성 근거를 확보했고 나머지 5건은 보류했다.
요청 CWE를 직접 뒷받침하는 자동 경고는 이번 설정에서 0/7이며, 2건의 근거는 함수 간 소스 검토에서 얻었다.
원 라벨·기존 검증 68/32 분류·20B 결과는 유지한다. 별도 잠정 sidecar를 보존했으며 A/B/C 모델 호출과 성능 재계산은 하지 않았다.


갱신일: 2026-10-14 (Asia/Seoul). 보고 범위는 보존된 20B 학습·평가·prefix 진단·원천 패치 검수와 후속 모델 준비다.
**학습 실행과 adapter 저장은 정상 완료됐지만, 목표한 취약점 탐지 성능은 아직 확보하지 못했다.**
학습 손실, 출력 형식 준수, 라벨 신뢰도, 탐지 판단을 각각 평가한다. 이번 보고서 갱신에서는 GPU 실험을 추가로 실행하지 않았다.

## 현재 결과와 판정

| 구분 | 관측과 판정 |
| --- | --- |
| 학습 실행 | `b200-ddp2-step100-v3`: 두 rank 모두 100 optimizer steps 완료, 평균 train loss 0.12981680523604155, adapter 저장·동일성 확인. 실행 완료 기준 충족 |
| 출력 형식 | 같은 입력의 paired 진단에서 adapter invalid 30/100 → 0/100 (native → training prefix). 형식 정합성 문제를 확인했으나 재학습으로 해결한 것은 아님 |
| 데이터 라벨 | 100건 원천 검수 완료, 이진 판정 68건·보류/제외 32건. 원 라벨 15건을 요청 CWE·함수 범위 기준 양성→음성으로 수정한 별도 sidecar 보존 |
| 탐지 성능 | 검증 68건·training prefix·dynamic 조건의 adapter TP=7, FN=9, FP=14, TN=38; F1=37.84%. 절대 성능 부족 |
| 일반화·실용성 | 반복 분석한 개발 표본이며 독립 최종 test가 아님. 사전 합의한 실용 성능 통과선과 일반 능력 유지 검증 미확보 |

## 실험 환경과 재현 조건

| 항목 | 확인한 구성 |
| --- | --- |
| 확인 시각 | 2026-10-14T06:27:08.387614+09:00 (KST) |
| OS / kernel | Ubuntu 24.04.3 LTS / 6.8.0-100-generic |
| CPU | AMD EPYC 9365 36-Core Processor × 2 sockets; OS 노출 논리 CPU 72, NUMA 2 |
| 시스템 RAM | MemTotal 2,373,247,804 KiB ≈ 2,263.3 GiB (OS 관측값) |
| GPU / VRAM | NVIDIA B200 × 2; 각 183,359 MiB (약 179.06 GiB); CUDA capability 10.0 |
| 드라이버 / GPU 연결 | 580.95.05 / nvidia-smi topo의 GPU0↔GPU1 NV18; 실측 통신 대역폭은 미검증 |
| 모델 저장소 | 공유 Lustre 볼륨; 가중치·데이터·adapter·원본 결과는 Git 제외 |
| 실행 구분 | 20B 학습: 두 rank DDP 모델 복제; 평가: 한 모델을 GPU0·1에 분할, base → adapter |
| 후속 대형 모델 | 추론: 두 GPU 분할; 학습: FSDP2 후보이며 실제 역전파·메모리 적합성 미검증 |

CPU·RAM·OS·연결 정보는 이번 읽기 전용 조회값이다. 이를 과거 실행 당시 상태로 소급 확정하지 않는다.
GPU·학습 패키지·분산 설정은 아래 보존 이력의 원 실행 기록과 함께 읽는다.
OS 노출 CPU 수를 물리 호스트 전체 자원 할당량이라고 단정하지 않는다.

| 환경 | Python | PyTorch 배포 메타데이터 | Transformers | TRL | PEFT | Accelerate |
| --- | --- | --- | --- | --- | --- | --- |
| 20B 실행 환경 | 3.12.3 | 2.14.1 | 4.56.2 | 0.22.2 | 0.21.2 | 1.15.0 |
| 후속 3개 모델 CPU 준비 환경 | 3.12.3 | 2.12.1+cu130 | 5.9.0 | 1.5.1 | 0.19.1 | 1.13.0 |

20B 환경의 원 실행 기록은 PyTorch CUDA wheel 13.0을 기록한다. 위 `2.14.1`은 현재 배포 메타데이터 표시값이다.
20B Unsloth 2026.9.14 / Zoo 2026.9.9, bitsandbytes 0.50.2, Triton 3.8.0, torchao 0.18.0이며,
Harmony 채점은 별도 CPU 환경의 openai-harmony 0.0.8을 사용한 보존 기록이다.
후속 환경은 기존 Mistral 환경을 CPU 준비에 재사용했으며 이번에 패키지를 설치하거나 20B 환경을 바꾸지 않았다.
A6000은 [별도 실험표](A6000_EXPERIMENT_TABLES.md)에 보존된 환경만 인용한다. 이번 작업에서 A6000 현장 환경을 재조회하지 않았다.

20B 학습은 NF4·double quantization·BF16 compute, LoRA r=8/alpha=16/dropout=0, LR=2e-4,
sequence length=1024, seed=3407, rank별 batch=1·accumulation=2·전체 batch=4였다.
동결 train 10,000건 중 유효 8,525건을 사용했으며 학습은 약 0.047 epoch에 해당한다.
100-step 완료나 낮은 train loss는 충분한 학습량·수렴·일반화 성공을 보장하지 않는다.
실행 소스는 당시 HEAD `0e51218d936a665c2aa2ac32e2dc934ca0efb543`와 미커밋 변경의
`source-identity.json` 및 `executed-source/`로 식별한다. 이번 문서 편집 기준 HEAD는
`269bd24b9b302e793a08369857c0acb1f5567fcf`이며 원 학습의 실행 revision과 다르다.

## 형식 문제: 학습 completion 경계와 추론 prefix의 불일치

10,000건 감사에서 학습 template·token ID·mask는 보존 실행과 일치했다. 기존 final-only loss mask는
assistant의 Harmony header 및 analysis→final 전환 토큰을 가리고, 주로 JSON 답변과 종료 토큰을 학습시켰다.
유효 8,525건 중 완전한 답변·종료 토큰은 8,510건, 잘린 정답은 15건이었다.
native 추론은 assistant 시작점에서 생성하지만 학습의 첫 supervised token 앞에는 빈 analysis와 final header가 있었다.
이 차이는 형식 실패의 유력한 기전이며, mask 재학습을 통한 인과 검증은 아직 하지 않았다.

동일 validation100에서 모델별 native/training prefix를 비교한 400회 진단은 GPU0·1 분할,
base → adapter 순서, DynamicCache, max_new_tokens=65,536으로 수행했다.
각 입력은 `sha256(3407:input_id)` 기반 seed를 모든 조건에 동일하게 적용했다.
training prefix에는 채널 구조만 제공했고 정답 JSON이나 정답 라벨은 넣지 않았다.

| 모델 | Prefix | 유효 | Invalid | Harmony 파싱 | Final 누락 | Schema 오류 |
| --- | --- | --- | --- | --- | --- | --- |
| base | native | 73 | 27 | 8 | 14 | 5 |
| base | training_prefix | 94 | 6 | 0 | 0 | 6 |
| adapter | native | 70 | 30 | 29 | 1 | 0 |
| adapter | training_prefix | 100 | 0 | 0 | 0 | 0 |

위 진단 400회는 모두 native EOS로 종료했다. 따라서 이 조건에서 관측한 형식 실패를 생성 상한 도달로 설명할 수 없다.
짧은 상한을 포함한 이전 전체 평가의 길이 부족과는 구분한다. 학습 prefix에서 형식이 맞았다는 사실은
모델이 native 시작점부터 Harmony를 스스로 생성할 수 있게 됐다는 증거가 아니다.

## 데이터 라벨 문제: 원천 패치와 요청 범위의 대조

라벨은 제공 함수와 요청 CWE의 조합을 대상으로 검수했다. 패치가 다른 함수의 결함을 고쳤거나,
같은 커밋의 다른 CWE가 전파됐거나, 호출자·자료구조 문맥이 부족한 사례를 구분했다.
확정 68건은 양성 16·음성 52건이다. 음성은 해당 범위에서 요청 CWE가 관측되지 않았다는 뜻이며 프로젝트 전체의 안전을 뜻하지 않는다.
보류 32건은 문맥 불충분 11, CWE·문맥 불충분 6, CWE 대응 불확실 1, 부적절한 평가 대상 10,
원천 불일치 2, 원천 미확인 2건이다. 보류를 음성으로 강제하지 않는다.

원 라벨·원 예측은 그대로 두고 `verified-labels-v3.jsonl`로 재채점했다.
동일한 68개 ID에서 adapter F1은 원 라벨 기준 46.15%에서 검증 라벨 기준 37.84%로 내려갔다.
라벨 정정이 성능을 높였다고 해석할 수 없다. 원 100건과 확정 68건을 직접 비교하면 표본 구성 변화가 섞인다.
검수는 주 담당자의 수동 정적 검토이며 비맹검·비독립 검토다. 취약점 실행 재현은 하지 않았으므로,
검증 라벨에도 이 범위의 불확실성이 남는다. 이미 분석한 100건은 개발 진단용으로 유지한다.

## 형식을 맞춘 뒤 남은 미탐·오탐

아래는 **training prefix / dynamic / 검증 라벨 68건**의 결과다. native·static 결과로 전용하지 않는다.
행은 정답, 열은 예측이며 uncertain(판단 유보)과 invalid(형식 실패)를 별도 열로 유지한다.

| 모델 | 정답 | present | not_observed | uncertain | invalid |
| --- | --- | --- | --- | --- | --- |
| base | present (16) | 2 | 0 | 12 | 2 |
| base | not_observed (52) | 5 | 6 | 37 | 4 |
| adapter | present (16) | 7 | 9 | 0 | 0 |
| adapter | not_observed (52) | 14 | 38 | 0 | 0 |

| 모델 | TP | FN¹ | FP | TN | U | I | Precision | Recall² | F1² | 이진 응답률 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 2 | 0 | 5 | 6 | 49 | 6 | 28.57% | 12.50% | 17.39% | 19.12% |
| adapter | 7 | 9 | 14 | 38 | 0 | 0 | 33.33% | 43.75% | 37.84% | 100.00% |

¹ FN 열은 명시적으로 음성을 출력한 미탐이다. base의 FN=0은 미탐 문제가 없다는 뜻이 아니다.
정답 양성 16건 중 base는 12건을 유보하고 2건에서 형식에 실패해 2건만 탐지했다.
² P=TP/(TP+FP), R=TP/전체 정답 양성, F1=2TP/(TP+FP+전체 정답 양성)으로 계산한다.
양성의 유보·형식 실패도 recall 분모에 남기며, 지표가 정의되지 않는 경우는 0 대신 미정으로 표시한다.

adapter는 유효한 이진 응답을 68/68건 생성했지만 양성 16건 중 9건을 놓쳤고 음성 52건 중 14건을 양성으로 판정했다.
관측상 답변을 확정하는 경향은 강해졌으나 올바른 취약점 판단이 충분히 따라오지 못했다.
내부적으로 무엇을 학습했는지는 이 decision-only 출력만으로 확정하지 않는다.

| 잔여 오류 예시 | 원천 패치 검수에서 확인한 근거 | 다음 개선 대상 |
| --- | --- | --- |
| FN: `parse`, CWE-476 | skipSpaces의 NULL 반환을 검사하기 전에 memcmp/역참조; 패치가 NULL 검사 추가 | 포인터 반환값·검사·사용 경로를 연결하는 예제 |
| FN: `TightDecoder::FilterGradient24`, CWE-787 | width=0에도 첫 픽셀 쓰기; 패치가 x&lt;width 반복 안으로 이동 | 0·경계값과 반복문 진입 조건 |
| FN: `queue_push`, CWE-119 | 확장 후 길이로 이전 버퍼를 복사; 패치가 original_length 보존 | 할당 크기·복사 길이·상태 갱신 순서 |
| FP: `rfc_send_pn`, CWE-125 | 수정 대상은 수신 길이 검사이며 이 함수는 고정 형식 송신 frame 구성 | 같은 프로젝트의 취약/비취약 함수 대조 |
| FP: `SFDGetSpiros`, CWE-416 | 이 함수의 NULL/빈 목록 결함과 다른 함수의 use-after-free를 구분해야 함 | 결함 존재와 요청 CWE 일치 여부를 분리 |

이 사례는 정적 검수에 따른 분석자 해석이다. 모델의 생성된 추론 근거나 사고 과정을 관측한 것으로 쓰지 않는다.

## 기존 정적·동적 평가와의 관계

기존 native 평가도 정적·동적 × base/adapter × 6개 생성 상한에서 총 2,400회 완료됐다.
이는 동일 validation100의 반복이며 2,400개의 독립 표본이 아니다. 아래는 65,536-token 상한의
strict 채점·**원 라벨** 예시이고, 위 prefix 진단 및 검증 라벨 표와 조건이 다르다.
보고서에서는 유보를 제외한 조건부 recall/F1과 혼동하지 않도록 전체 정답 양성 분모로 다시 계산했다.

| Cache | 모델 | 완료 | TP/FN/FP/TN | U/I | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| static | base | 100 | 12 / 17 / 0 / 22 | 23 / 26 | 100.00% | 24.00% | 38.71% |
| static | adapter | 100 | 13 / 27 / 6 / 29 | 0 / 25 | 68.42% | 26.00% | 37.68% |
| dynamic | base | 100 | 8 / 19 / 1 / 23 | 29 / 20 | 88.89% | 16.00% | 27.12% |
| dynamic | adapter | 100 | 10 / 22 / 6 / 24 | 0 / 38 | 62.50% | 20.00% | 30.30% |

정적 표기는 당시 Unsloth 기본 정적 경로이며 실제 cache 클래스 계측은 없었다.
동적 실행은 DynamicCache 관측을 요구했다. 한 번의 sampling 차이를 cache 자체의 인과 효과로 단정하지 않는다.
전체 상한별 행렬과 A6000 대조는 [캐시 비교 기록](CACHE_COMPARISON.md)에 연결한다.
이 표본에서 측정하지 못한 GPU allocator peak나 속도는 추정하여 채우지 않는다.

## 5개 모델 비교 실험표

후속 비교 대상은 GPT-OSS-20B, Qwen3-Coder-Next 80B, Mistral Small 4 119B,
GPT-OSS-120B, Llama 3.1 405B Instruct다. 기존 20B 진단 점수를 다른 모델의 공통 조건 결과처럼 복사하지 않는다.
아래 빈 칸은 미실행이며 0점이 아니다. Llama는 양자화 결정까지 계속 대기한다.

| 모델 | 현재 가중치/정밀도 | 준비·진입 상태 | 공통 Base P/R/F1 | 공통 Adapter P/R/F1 |
| --- | --- | --- | --- | --- |
| GPT-OSS-20B | NF4 / BF16 compute | 100-step 학습·기존 정적/동적 평가 완료; 아래 진단 성능과 공통 비교를 분리 | — | — |
| Qwen3-Coder-Next 80B | BF16 | 가중치·CPU 준비 완료; 실제 적재·1-step 검증 후 진입 | — | — |
| Mistral Small 4 119B | FP8 원본 + BF16 로컬 파생본 | 가중치·CPU 준비 완료; 실제 적재·1-step 검증 후 진입 | — | — |
| GPT-OSS-120B | MXFP4 배포; 학습은 BF16 dequant 후보 | 가중치·CPU 준비 완료; 실제 적재·1-step 검증 후 진입 | — | — |
| Llama 3.1 405B Instruct | 양자화 방식 미정 | 다운로드·양자화·학습 대기 | — | — |

| 모델 | 조건 | 정적 P/R/F1 | 동적 P/R/F1 | 공통 비교 상태 |
| --- | --- | --- | --- | --- |
| GPT-OSS-20B | base | — / — / — | — / — / — | 공통 조건 미실행 |
| GPT-OSS-20B | adapter | — / — / — | — / — / — | 공통 조건 미실행 |
| Qwen3-Coder-Next 80B | base | — / — / — | — / — / — | 공통 조건 미실행 |
| Qwen3-Coder-Next 80B | adapter | — / — / — | — / — / — | 공통 조건 미실행 |
| Mistral Small 4 119B | base | — / — / — | — / — / — | 공통 조건 미실행 |
| Mistral Small 4 119B | adapter | — / — / — | — / — / — | 공통 조건 미실행 |
| GPT-OSS-120B | base | — / — / — | — / — / — | 공통 조건 미실행 |
| GPT-OSS-120B | adapter | — / — / — | — / — / — | 공통 조건 미실행 |
| Llama 3.1 405B Instruct | base | — / — / — | — / — / — | 양자화 대기 |
| Llama 3.1 405B Instruct | adapter | — / — / — | — / — / — | 양자화 대기 |

총 20개 조건(5모델 × base/adapter × static/dynamic)의 결과 자리를 마련했다.
모델별 cache 지원 확인 후 미지원은 N/A로 기록한다. 실행 순서는 각 모델에서 정적 base → adapter,
그다음 동적 base → adapter를 기본 비교 순서로 두며, 각 학습 전 baseline을 먼저 확보한다.
Llama를 자동 실행 대기열에 넣지 않는다. 나머지 세 모델도 표 작성만으로 학습이 시작되지는 않는다.

각 조건에는 run ID, 모델/adapter revision·hash, dataset/label/prompt hash, seed, 실제 cache 클래스,
양자화·dtype·장치 배치, TP/FN/FP/TN/U/I, P/R/F1·이진 응답률을 기록한다.
GPU0·1별 allocated/reserved 및 각각의 peak, nvidia-smi 장치 전체 메모리 표본,
생성 토큰 수·시간·tokens/s, 학습 시간·peak, OOM/중단 상태도 구분해 기록한다.
로컬 원본 로그가 기준이며 W&B는 실제 연결·기록 확인 후 활성으로 표시한다.

Qwen·Mistral·120B 공식 revision은 다음과 같이 고정했고 58개 shard의 공식 SHA-256을 확인했다.

| 모델 | 공식 저장소 | 고정 revision |
| --- | --- | --- |
| Qwen3-Coder-Next 80B | Qwen/Qwen3-Coder-Next | `a7fbcb5c0e12d62a448eaa0e260346bf5dcc0feb` |
| Mistral Small 4 119B | mistralai/Mistral-Small-4-119B-2603 | `a11f36bebf709121056b1dbcc943d1c6afbe494d` |
| GPT-OSS-120B | openai/gpt-oss-120b | `b5c939de8f754692c1647ca79fbf85e8c1e70f8a` |

Qwen 기존 로컬 template는 보존하고 공식 template를 별도 실행 폴더에 준비했다.
Mistral BF16 파생본은 구조·계보만 확인했으며 변환 수치 재현은 미실행이다.
후속 세 모델의 config·tokenizer·meta 구조와 합성 형식 9건은 CPU 검사를 통과했다.
GPU 적재·역전파·adapter 저장/재적재는 아직 미검증이다. 모델 크기·정밀도·target 수·데이터 예산 차이를
공개하고, 동일 LoRA rank만으로 동등한 학습 용량이라고 주장하지 않는다.

## 다음 실험에서 개선할 항목과 완료 기준

| 순서 | 개선할 변수와 통제 | 다음 단계로 넘어갈 근거 |
| --- | --- | --- |
| 1. 형식 정합성 | 공식 template에서 native prompt와 supervised completion 경계를 일치시키고 header·채널·종료 토큰을 포함한 loss mask 검사. 같은 데이터·seed·예산에서 기존 final-only와 수정 mask를 대조 | 잘린 정답 15건 처리, 전체 학습 입력 경계 감사, 정답 누출 없음. native 출력의 format-valid 비율과 탐지 지표를 함께 보고 |
| 2. 라벨·분할 | 함수 범위·CWE·패치 전후 계보를 확인한 별도 학습 자료 사용; 보류 사례는 분리. 프로젝트/커밋/복제 함수 단위 중복 제거 | train/dev/test 중복 감사와 라벨 근거 manifest 고정. 현재 분석 100건은 개발용으로 유지하고 새 최종 test 확보 |
| 3. 판단 학습 | 누락한 NULL·경계·길이 추적 예제와 안전한 대응 예제, 요청 CWE가 다른 hard negative를 별도 학습 split에서 구성 | 미탐·오탐을 CWE별로 대조. 필요할 때만 근거 supervision을 별도 실험으로 추가하고 형식·데이터·학습량을 한꺼번에 바꾸지 않음 |
| 4. 학습량·설정 | 수정 20B 기준선부터 1→10→100-step 확인 후 dev 추세로 예산 결정; 기존 연구의 선택적 block 대상은 별도 확정 | 유한 loss/gradient, 동결 가중치 유지, 두 GPU 동작, adapter 저장/재로딩 일치. 작은 train loss만으로 checkpoint 선택하지 않음 |
| 5. 모델 확장 | 동일 평가 ID·의미상 지시·라벨·공통 생성 예산, 각 모델 native template, base/adapter 간 동일 정밀도; 세 후속 모델에 순차 적용 | 2-GPU 적재와 1-step 통과 후 정식 평가. 일반 능력 유지·기권·invalid와 속도/메모리를 함께 기록 |
| 6. 캐시·용량 | static/dynamic 실제 지원·클래스 확인, 같은 seed 조건으로 비교; 공통 성능 시험과 장문 수용량 시험 분리 | 지원 안 되는 cache는 N/A, OOM은 실행 실패로 보존. 반복 seed/공통 완료 ID 확인 전 작은 차이를 일반화하지 않음 |

후속 LoRA r=16/alpha=32, sequence length=2048, LR=1e-4 등은 준비 단계 후보이며
기존 20B 학습 조건과 다르다. [실험 계획](FINETUNING_EXPERIMENT_PLAN.md)의 2026-10-13 준비 기록과
장비별 `experiment-plan.json`을 기준으로 데이터·target·예산을 동결한 뒤 실행한다.
이번 요청은 보고서와 후속 실험 자리 마련이며 새 GPU 실행이나 자동 학습 예약을 만들지 않았다.

## 결론과 확인 한계

학습 파이프라인은 정상 완료했고 adapter의 이진 응답률과 개발 진단 성능은 base보다 개선됐다.
그러나 native 출력 형식 실패, 평가 라벨의 범위·CWE 불일치, 형식을 맞춘 뒤에도 남은 미탐·오탐은 별개의 문제다.
형식 또는 라벨만 고치면 탐지 성능 문제가 모두 해결된다고 볼 근거는 없다.
따라서 현 단계는 **학습 실행 검증 완료·탐지 성능 개선 필요**로 보고한다.
다음 실험에서는 형식 정합성, 검수 데이터, 판단 오류를 순차 통제하고 공통 조건에서 5개 모델을 비교한다.

## 근거와 보존

| 근거 | 저장 위치(저장소 루트 기준) |
| --- | --- |
| 20B 학습·저장 | `outputs/b200-ddp2-step100-v3/`의 rank별 training/runtime, adapter-save-verification, source-identity |
| 정적·동적 원 행렬 | 각 평가 run의 confusion-matrices.json; 캐시 비교 manifest와 문서 |
| Prefix paired 진단 | `outputs/b200-prefix-paired-validation100-20261012-v1/plan.json`, `summary.json` |
| Mask·정답 토큰 감사 | `.private/b200-harmony-cause-20261012/audit.json` |
| 원천 검수·재채점 | `.private/b200-prefix-label-review-20261013-v3/`의 verified-labels-v3.jsonl, rescored-metrics-v3.json |
| 후속 모델 준비 | `.private/b200-model-preparation-20261013/`의 experiment-plan, readiness-manifest, training-format-check |
| 이번 환경·비교표·검사 | `.private/b200-report-update-20261014/`의 environment-observation.json, five-model-comparison.json, report-validation.json |

원 평가·라벨·adapter를 수정하지 않았다. 아래 과거 문서는 당시 상태를 보존한 이력이다.
그 안의 ‘평가 미실행’ 및 ‘GPU0 단독 평가’ 설명은 2026-10-07~08 준비 상태이며 현재 상태가 아니다.

---

## 보존 이력: 2026-10-07~08 원 보고서

# B200 실험표 — GPT-OSS-20B, 두 GPU DDP

기록일: 2026-10-07 (Asia/Seoul).
이 표는 B200의 실제 runtime·rank별 training receipt·저장 검증·평가 준비 artifacts에서 작성했다.
[A6000 표](A6000_EXPERIMENT_TABLES.md)는 보존된 원 실행의 별도 표다.
실행 방법과 후보 프레임워크 문서는 [B200 재현 레시피](B200_REPRODUCTION_RECIPE.md)에 둔다.

여기서 환경별 구조는 학습 실행 구성·분산·메모리 관리의 차이를 뜻한다.
GPT-OSS 기본 아키텍처나 LoRA 대상 레이어를 새로 바꾼 실험은 아니다.
별도 단일 GPU 100-step 학습은 생략했다.

## 1. B200 환경과 도구 구성

| 항목 | B200 실제 환경 |
| --- | --- |
| GPU | NVIDIA B200 2장, 각183,359 MiB, CUDA capability10.0 |
| 드라이버 | 580.95.05 (이번 재조회) |
| Python | 외부 관리 서버의3.12.3; A6000의3.12.13과 차이 승인·기록 |
| PyTorch / CUDA wheel | 2.14.1+cu130 / CUDA13.0 |
| Transformers / TRL / PEFT | 4.56.2 / 0.22.2 / 0.21.2 |
| Unsloth / Zoo | 2026.9.14 / 2026.9.9 |
| Accelerate / bitsandbytes / Triton / torchao | 1.15.0 / 0.50.2 / 3.8.0 / 0.18.0 |
| Harmony scorer | 별도 CPU 환경, Python3.12.3 / openai-harmony0.0.8 |
| 패키지 대조 | native113개·scorer11개 버전 및 해당 Git provenance를 원 기록과 대조 |
| 분산 | torchrun, 한 노드·두 rank, PyTorch DDP, NCCL |
| 장치 배치 | rank0→GPU0, rank1→GPU1; GPU마다 모델 복제본 |
| 저장 책임 | 최종 adapter·공용 결과는 rank0, 실행 상태·로그는 rank별 |
| 자동 재시도 | torchrun max-restarts=0; 실패 run을 보존하고 새 ID 사용 |
| 원본 저장 경계 | model/data/outputs/artifact 및 장비별 설정은 Git 제외 |

| 구성요소 | 이번 실행에서 맡는 역할 |
| --- | --- |
| Transformers·tokenizer | GPT-OSS 모델 구조와 날짜를 고정한 chat template |
| Unsloth / bitsandbytes | 모델 로딩·지원되는 계산 패치 / NF4 4bit 가중치 |
| PEFT / Unsloth get_peft_model | 같은 LoRA 대상·크기와 학습 파라미터 준비 |
| TRL SFTTrainer | 학습·logging·optimizer/scheduler 진행 |
| Unsloth train_on_responses_only | assistant final 위치만 supervised labels로 유지 |
| Accelerate / PyTorch DDP | Trainer의 분산 실행 연결·gradient 동기화 |

Unsloth는 Trainer·모델 계산도 패치할 수 있으므로 표는 주 역할을 설명하며 완전히 독립된 경계를 뜻하지 않는다.
두 GPU DDP는 두 장의 VRAM을 하나의 모델 저장 공간으로 합치는 방식이 아니다.

## 2. 실제 100-step 학습 조건

| 조건 | B200 `b200-ddp2-step100-v3` |
| --- | --- |
| base / revision | `unsloth/gpt-oss-20b-unsloth-bnb-4bit` / `093fba6992ef5a7152481afec0bdfca1ac486998` |
| 양자화 | NF4·double quantization·BF16 compute; verified offline snapshot |
| 데이터 | 동결 v5 train10,000 / validation1,000; test500 미사용 |
| token/mask 검사 | 원 A6000의10,000건 감사와 일치; 유효8,525·제외1,475·partial15 |
| 입력 길이 / 날짜 / seed | 1024 / 2026-10-04 / 3407 |
| GPU당 batch / accumulation | 1 / 2 |
| 전체 batch / steps | 1×GPU2×accum2=4 / optimizer100회 |
| 계획 표본 제시 수 / 입력 token 상한 | 400 / 409,600 |
| LoRA | r8, alpha16, dropout0, bias=none, q/k/v/o/gate/up/down 대상 유지 |
| trainable parameters / tensors | 92,454,912 / 3,264 |
| optimizer / LR / scheduler | adamw_8bit / 2e-4 / linear |
| warmup / weight decay | 5 optimizer steps / 0.001 |
| loss target | 원 공식 final-only mask, assistant JSON+빈 thinking |
| activation checkpointing | **해제**; 설치된 Unsloth reentrant 방식과 sparse MoE DDP 감지의 충돌 회피 |
| ddp_find_unused_parameters | **True**; 입력에 따라 사용되지 않는 expert의 gradient 처리 |
| compiler override | 없음; activation checkpointing 해제와 컴파일 비활성화를 구분 |
| validation / W&B / 외부 timeout | 학습 중 비활성 / report_to=none / 원 실행처럼 추가하지 않음 |

A6000과 달라진 실행 변수는 GPU·드라이버, Python 패치, DDP sampler/reduction,
accumulation4→2, rank별 장치·저장 처리, activation checkpointing이다.
전체 batch는4로 유지했다. 속도 차이를 GPU만의 효과로 해석하거나 두 adapter SHA가 같아야 한다고 요구하지 않는다.

## 3. 실행 이력 — 실패도 별도 보존

| run | optimizer step | 결과 | 원인 / 다음 변경 |
| --- | ---: | --- | --- |
| `b200-step100-v1` | 미실행 | 데이터·환경 준비만 완료 | 단일 GPU 본 학습을 생략 |
| `b200-ddp2-step100-v1` | 0 | 런처 단계 실패 | torchrun이 --run을 자신의 옵션으로 해석; 명령 구분자 -- 검증 후 새 run |
| `b200-ddp2-step100-v2` | 1 | DDP reduction 실패 | sparse MoE unused parameter; checkpointing 해제·unused 감지 활성화 후 새 run |
| `b200-ddp2-step100-v3` | 100 | **학습·저장·검증 완료** | 두 rank 동기화·저장 가중치 일치 확인 |

실패한 v1/v2의 결과를 v3와 합산하지 않는다. v3 학습에 사용된 소스는
`source-identity.json`의 SHA 및 `executed-source/` 복사본으로 보존했다.
후속 init/default 경로 보완은 그 실행에 사용된 코드라고 소급 기록하지 않는다.

## 4. 두 rank의 학습 결과

| 지표 | rank0 / GPU0 | rank1 / GPU1 |
| --- | ---: | ---: |
| 완료 optimizer steps | 100 | 100 |
| 평균 train loss | 0.12981680523604155 | 0.12981680523604155 |
| 마지막 step loss | 0.0814 | 0.0814 |
| Trainer train runtime (초) | 277.8209 | 275.9026 |
| epoch | 0.04691531785127844 | 0.04691531785127844 |
| 변경 tensor / 전체 trainable tensor | 3,176 / 3,264 | 3,176 / 3,264 |
| peak PyTorch allocated (bytes) | 27,308,960,256 | 26,804,643,328 |
| peak PyTorch reserved (bytes) | 28,177,334,272 | 28,020,047,872 |
| source / effective records | 10,000 / 8,525 | 10,000 / 8,525 |

Trainer runtime은 전체 설치·다운로드·준비·런처 시간을 뜻하지 않는다.
두 rank의 시간을 더해 wall time으로 보고하지 않는다.
PyTorch allocated/reserved와 nvidia-smi의 장치 전체 메모리 값도 구분한다.

| B200 100-step 구간 (두 rank 동일) | 평균 logged train loss | 마지막 loss | 마지막 logged LR |
| --- | ---: | ---: | ---: |
| 1–25 | 0.265464 | 0.1081 | 0.00016000 |
| 26–50 | 0.086096 | 0.0499 | 0.00010737 |
| 51–75 | 0.087908 | 0.0706 | 0.00005474 |
| 76–100 | 0.079804 | 0.0814 | 0.00000211 |

| 검증 | 실제 결과 |
| --- | --- |
| rank별 장치 / NCCL 합산 | GPU0/1 배치·world_size2 확인, 합산3.0 |
| 입력·마스크 / 초기 LoRA hash | 두 rank 일치 |
| 최종 LoRA hash | 두 rank 완전 일치 |
| 실제 파라미터 변경 | 두 rank 모두3,176 tensor 변경 |
| 저장된 adapter | 모든3,264 key·tensor가 학습 직후 PEFT state와 일치 |
| launcher 종료 코드 | 0 |
| 종료 직후 GPU 메모리 | 두 장 모두0 MiB 관측 |
| 관련 CPU 회귀 검사 | 28개 통과 |

최종 adapter SHA256: `34b298f580d1bcdd36981172b334246d10ce40a09658995ef5841d38018ee348`.
학습 완료는 탐지 성능 개선을 뜻하지 않는다. 아래 생성 평가가 아직 미실행이다.

## 5. base·adapter 자유 생성 평가표 — 준비 완료, 생성 미실행

평가 ID는 `b200-ddp2-step100-v3-{base,adapter}-validation100`이다.
같은 validation100(양성50·음성50), 입력232–980토큰, 여섯 데이터 해시·새 adapter SHA 대조와
초기 Harmony scorer 실행을 완료했다. 각 모델600회, 총1,200회 계획이다.
실제 GPU 생성 worker는 아직 실행하지 않았고 raw 결과 파일은 두 arm 모두0개다.

| 모델 | 생성 상한 | 완료/계획 | pending | TP / FN / FP / TN | uncertain / invalid | 상태 |
| --- | --- | ---: | ---: | --- | --- | --- |
| base | 128 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| base | 512 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| base | 2048 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| base | 65536 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| base | 130000 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| base | context-minus-input | 0/100 | 100 | — | — | 준비 완료·미실행 |
| adapter | 128 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| adapter | 512 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| adapter | 2048 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| adapter | 65536 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| adapter | 130000 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| adapter | context-minus-input | 0/100 | 100 | — | — | 준비 완료·미실행 |

`—`는 평가 미실행이며 성능0%를 뜻하지 않는다. 초기 scorer JSON의0 행렬도 예측 결과가 아니다.
추후 strict·semantic 행렬을 각각 기록하고 uncertain·invalid·pending을 분리한다.
context-minus-input은 각 입력별 `131072-input_tokens`이다.
native sampling·medium reasoning·native EOS·fresh-process-per-model-budget-v2를 유지하고
gold/final-prefill·추가 generate kwargs·외부 timeout은 추가하지 않는다.
이 문서 갱신에서는 학습이나 생성 평가를 새로 실행하지 않았다.

## 6. 근거 위치와 상태를 읽는 기준

| 근거 | 프로젝트 내 위치 |
| --- | --- |
| 학습 조건 / 실행 source SHA | `outputs/b200-ddp2-step100-v3/config.json`, `source-identity.json`, `executed-source/` |
| 실행 상태·수치 | 같은 run의 `training-runtime.json`, `training.json`, `rank{0,1}/runtime.json`, `training.json`, `progress.json` |
| 저장·완료 검증 | 같은 run의 `adapter-save-verification.json`, `b200-verification.json`, `launcher-exit.json` |
| 환경 대조 | `outputs/b200-{native,score}-environment.json`, `b200-gpu-preflight.json` |
| 평가 준비 | 각 평가 run의 `prepared.json`, `confusion-matrices.json`; 학습 run의 `evaluation-preparation-summary.json` |
| 평가 실행용 config | `configs/b200-ddp2-step100-v3-{base,adapter}-validation100.json` |

Unsloth Git: `5971d280d4b645c8d470d6bb3171b082c4d4d2b8`.
Zoo Git: `867a86383371ebeb8ab1948d085540d134c07b4c`.
실행 저장소 HEAD: `0e51218d936a665c2aa2ac32e2dc934ca0efb543`에 당시 uncommitted DDP 변경을 적용했다.
따라서 HEAD만으로 실행 코드를 재현할 수 없고 source-identity 및 보존한 소스를 함께 사용해야 한다.
실행 명령은 같은 run의 `launcher.json`에 보존된
`bash scripts/b200/run-ddp.sh b200-ddp2-step100-v3`이다.

training/config의 `status=prepared`는 초기화 당시 상태다. 완료 여부는 runtime·training·verification으로 읽는다.
그 config의 generation2건·5상한은 원 training config에서 상속된 과거 진단 설정이며
현재100건·6상한 평가는 위 별도 평가 config가 기준이다. 원 실행 artifacts는 이 문서 갱신에서 수정하지 않는다.

공유 표에는 개인 절대 경로·접속값·원본 메시지를 넣지 않는다.
LLaMA-Factory·Axolotl은 [레시피14절](B200_REPRODUCTION_RECIPE.md#14-llama-factoryaxolotl-후보-비교--문서-준비만)의 문서 조사만 수행했고 설치·실험하지 않았다.


### 2026-10-08: 공용 환경 파일의 GPU 선택 설명

`outputs/b200-runtime-env.sh`에는 보존된 단일 장치 기본값 `CUDA_VISIBLE_DEVICES=0`이 있다.
실제 학습 launcher `run-ddp.sh`는 source 직후 `0,1`로 덮어쓰고 두 rank를 실행한다.
v3의 rank0·rank1 완료 기록은 각각 `world_size=2`, `global_step=100`이다.
평가 launcher에는 기존 단일 장치 선택을 명시했다. GPU 없는 CPU 대역 검증에서
학습 자식 프로세스에는 `0,1`과 `--nproc-per-node=2`, 평가에는 `0`이 전달됨을 확인했다.
공용 환경 파일의 기존 변수 값과 완료된 실행 artifacts는 바꾸지 않았고 GPU 재실행은 하지 않았다.

## 7. 2026-10-08 Git 공유 준비

두 GPU 100-step 완료와 저장 검증 결과를 기존 산출물에서 다시 확인했다. 자유 생성 평가는 여전히 0/1,200회다.
학습 당시 `train_ddp.py` SHA256은 `cdd8c64aa3b32a70d3f0c29474672a33d82a61cb394b9d6ea1c071438c55491f`이며,
원 실행 소스와 `source-identity.json`은 해당 run의 Git 제외 위치에 보존한다.
공유 코드는 학습 후 초기화·실행 경로 보완과 이번 타입 표기·서식 정리를 포함하므로, 새 커밋을 원 학습의 실행 revision으로 소급 표시하지 않는다.

CPU 검증은 루트 manifest·lock의 개발 도구를 설치한 별도 비공개 환경에서 수행하고,
기존 native 환경의 라이브러리를 읽기 전용으로 참조했다. GPU는 검증 프로세스에 노출하지 않았다.
pytest 597개, Ruff lint·format, mypy, DDP 실행 셸 문법과 Git diff 공백 검사를 통과했다.
검증 로그는 `.private/b200-git-publish-20261008/`에 보존한다. 학습 환경과 기존 adapter·동결 데이터·평가 입력은 변경하지 않았다.
