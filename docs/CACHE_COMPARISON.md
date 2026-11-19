# A6000 / B200 정적·동적 캐시 비교

질문은 캐시 방식에 따른 생성 완료 가능성과 최종 보안 판단 품질의 차이다.
장비 × 캐시 × 모델(base/adapter) × 생성 상한을 분리한다. 각 조건은 동일한
validation100(양성50/음성50)을 사용하고 strict/semantic을 각각 채점한다.
원래 상한 128, 512, 2048, 65536, 130000, context-minus-input을 유지한다.
한 모델당600호출, B200 동적 추가 평가 전체1200호출이며 새 학습은 없다.
최종 test500은 사용하지 않는다.

## 통제 및 해석

- B200은 각 모델을 GPU0·1에 balanced로 나눠 로딩하며 base 완료 후 adapter를 실행한다.
- 정적/native 평가의 frozen-inputs/prompts/gold를 바이트 단위 복사하고 adapter 및
  원본7종 해시를 비교한다. 모델 revision, 샘플링, EOS, 날짜, 문맥, 입력 순서가 동일하다.
- native는 기존 Unsloth 기본 정적 경로이며 실제 클래스는 계측하지 않았다.
  dynamic은 공통 runner가 실제 DynamicCache 관측을 요구한다.
- 상한마다 새 프로세스를 사용한다. 첫 실패에서 다음 모델 실행을 멈추며 부분 조건은
  자동 재개하지 않는다. 원본·실패 로그를 남기고 새 실험으로 재설계한다.
- 기존 생성 timeout 없음 정책을 유지한다. 임의 토큰 상한 확대나 반복 재시도는 없다.
- 같은100건을 반복하므로600건을 독립 표본으로 취급하지 않는다. 샘플링 난수는 기존
  방식이며 완전한 paired-seed 실험이 아니다.
- A6000와 B200의 adapter 학습 이력이 다르므로 장비·캐시만의 효과로 해석하지 않는다.
- A6000 정적302/600 OOM, 동적600/600은 공개 문서의 기록이다. 원본 JSON은 별도로
  가져와 검증해야 하며 현재 static base의 confusion counts는 미확인이다.

## B200 준비 및 실행

진행 중인 native 평가 코드·출력을 수정하지 않고 별도 설정과 출력만 생성한다.

```bash
python3 scripts/b200/dynamic_evaluation.py prepare --run b200-ddp2-step100-v3
python3 scripts/b200/dynamic_evaluation.py plan --run b200-ddp2-step100-v3
```

기존 native 평가가 종료되고 GPU 프로세스가 없을 때 실행한다. 같은 controller 잠금과
GPU 프로세스 검사로 동시 시작을 거부한다. 두 모델 모두 GPU0·1 전체를 사용한다.

```bash
tmux new-session -d -s b200-dynamic-cache -c "$PWD" 'source outputs/b200-runtime-env.sh && configs/environments/cc-native-step100/.venv/bin/python scripts/b200/dynamic_evaluation.py run --run b200-ddp2-step100-v3 > outputs/b200-ddp2-step100-v3-dynamic-launch.log 2>&1'
```

동적 상태·모델별 로그: `outputs/b200-ddp2-step100-v3-dynamic-evaluation/`.
모델별 raw·receipt·행렬: `outputs/b200-ddp2-step100-v3-dynamic-{base,adapter}-validation100/`.
중단은 `tmux send-keys -t b200-dynamic-cache C-c`이며 자식 프로세스 그룹을 정리한다.
준비 이후 runner가 바뀌면 동적 평가를 거부한다. 새 후보를 별도 준비해야 한다.

## 비교 보고서

```bash
python3 scripts/b200/compare_cache.py --manifest docs/results/cache-comparison-manifest.json --output outputs/b200-ddp2-step100-v3-cache-comparison
```

`comparison.json`은 실제 JSON에 있는2×4행렬과 지표를 보존한다. 문서에서 가져온
A6000 집계는 provenance로 구분하며 미확보 행렬을 만들어내지 않는다.
`comparison.md`는 상한·채점별 비교표다. 진행 중 스냅샷은 최종 결과가 아니다.
A6000 원본을 가져오면 manifest의 references를 제거하고 해당 장비의 scorer JSON
경로를 sources에 등록한다. 같은 조건의 원본을 중복 등록하면 실패한다.

- precision = TP/(TP+FP)
- 조건부 recall = TP/(TP+FN), F1 = 2TP/(2TP+FP+FN)
- 전체 양성 탐지율 = TP/(완료 표본의 실제 양성 수): 양성의 uncertain/invalid를 포함한다.
- 완료 표본 정확도 = (TP+TN)/완료 수
- 판단율 = (TP+FN+FP+TN)/완료 수, 완료율 = 완료 수/100
- uncertain, invalid, pending을 별도 기록한다. 분모0은 null/—이며0점으로 치환하지 않는다.

부분 완료2/100의 recall1.0은 전체100건 성능이 아니다. OOM은 FN/invalid가 아니며
완료율 저하로 표시한다. 최종 비교는 같은 상한의 전체 완료 조건, 또는 원본에서 추출한
공통 완료 ID로 제한한다. 조건부 F1과 전체 판단율을 반드시 함께 해석한다.

## 정적 완료 후 동적 자동 실행

`scripts/b200/queue_dynamic.py --run b200-ddp2-step100-v3`는 정적 평가의 두 모델이
생성·채점을 모두 완료하고 controller 잠금과 GPU가 해제될 때까지30초마다 확인한다.
정상 완료를 확인하면 기존 동적 실행기로 GPU0·1 분산 로딩, base→adapter를 실행한다.
동적 완료 후 비교 보고서도 갱신한다. 실패·중단·미완료 정적 결과에서는 시작하지 않는다.
대기 시작 시 코드 해시를 동결하며 이후 변경 시 자동 진행을 거부한다.

```bash
tmux new-session -d -s b200-cache-chain -c "$PWD" 'source outputs/b200-runtime-env.sh && configs/environments/cc-native-step100/.venv/bin/python scripts/b200/queue_dynamic.py --run b200-ddp2-step100-v3 >> outputs/b200-ddp2-step100-v3-dynamic-evaluation/queue.log 2>&1'
```

동적 준비 후 실행하며 자동 대기와 수동 동적 실행을 함께 시작하지 않는다.
대기 상태는 `outputs/b200-ddp2-step100-v3-dynamic-evaluation/queue.json`,
로그는 같은 폴더의 `queue.log`다. 같은 queue receipt를 덮어 재시작하지 않는다.
`tmux send-keys -t b200-cache-chain C-c`로 대기 또는 후속 동적 평가를 중단한다.
서버·tmux 프로세스가 종료되면 대기 작업도 종료되며 자동 재부팅 복구는 하지 않는다.
