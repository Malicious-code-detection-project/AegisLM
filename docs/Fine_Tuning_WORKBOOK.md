## 1. 파인튜닝 전체 과정

우리 프로젝트의 목표는 다음과 같습니다.

> C/C++ 코드와 확인할 CWE를 입력하면, 코드에 근거한 분석 결과를 정해진 JSON 형식으로 출력하도록 기존 모델을 추가 학습한다.

파인튜닝은 모델을 처음부터 만드는 것이 아닙니다. 이미 언어와 코드를 학습한 base 모델의 출력 방식을 우리 과제에 맞게 조정하는 과정입니다.

단계                   하는 일                                           확인해야 할 것
━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. 과제·데이터 이해    입력과 정답, 데이터 분할을 확인                   무엇을 보고 무엇을 맞히는가?
─────────────────────  ────────────────────────────────────────────────  ──────────────────────────────────────────────────
2. 학습 데이터 변환    대화를 토큰으로 바꾸고 정답 영역을 지정           어느 토큰에서 학습 오차를 계산하는가?
─────────────────────  ────────────────────────────────────────────────  ──────────────────────────────────────────────────
3. 기준선·모델 준비    base 성능을 기록하고 LoRA 설정                    학습 전 성능은 어떻고, 어떤 파라미터를 바꾸는가?
─────────────────────  ────────────────────────────────────────────────  ──────────────────────────────────────────────────
4. 최소 학습 루프      소수 샘플로 forward → loss → backward → update    실제로 정답을 학습할 수 있는가?
─────────────────────  ────────────────────────────────────────────────  ──────────────────────────────────────────────────
5. 학습·검증           학습량을 늘리고 별도 validation으로 확인          외우기만 하는가, 새 데이터에도 적용되는가?
─────────────────────  ────────────────────────────────────────────────  ──────────────────────────────────────────────────
6. 저장·재로딩         adapter를 저장하고 다시 불러오기                  저장된 결과를 동일하게 사용할 수 있는가?
─────────────────────  ────────────────────────────────────────────────  ──────────────────────────────────────────────────
7. 최종 비교 평가      같은 평가 데이터로 base와 fine-tuned 비교         JSON 형식과 분석 품질이 실제로 좋아졌는가?

4단계의 핵심 동작은 이렇습니다.

학습 예시
→ 모델이 다음 토큰의 확률을 계산한다          [forward]
→ 정답 토큰에 준 확률로 오차를 계산한다      [loss]
→ 오차를 줄일 파라미터 변화 방향을 계산한다  [backward]
→ 학습 대상 파라미터를 조금 변경한다         [optimizer.step]

LoRA에서는 주로 추가한 작은 adapter 파라미터를 학습하고 base 파라미터는 고정합니다. QLoRA는 여기에 base 모델 양자화를 사용해 메모리 부담을
줄이는 방식입니다.

중요한 구분도 있습니다. 학습 코드가 끝까지 실행되는 것, loss가 낮아지는 것, 실제 생성 결과가 좋아지는 것은 각각 별도로 검증해야 합니다. 이전
실험을 이해할 때도 이 구분이 필요합니다.

## 2. 지금 시작할 1단계: 입력과 정답 이해하기

오늘의 목표는 간단합니다.

> 데이터 한 건을 보고 “모델이 받는 문제”와 “학습할 정답”을 구분할 수 있다.

### 실제 데이터 구조

현재 파일을 확인했습니다.

파일                레코드 수    역할
━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
train.jsonl            10,000    파라미터를 업데이트하는 학습 데이터
──────────────────  ───────────  ───────────────────────────────────────
validation.jsonl        1,000    학습 중 일반화 상태를 확인하는 데이터
──────────────────  ───────────  ───────────────────────────────────────
challenge.jsonl           500    최종 평가에 사용할 문제
──────────────────  ───────────  ───────────────────────────────────────
gold.jsonl                500    평가 문제에 대응하는 채점용 정답

challenge와 gold는 문제와 정답의 쌍입니다. 평가 샘플이 총 1,000개라는 뜻은 아닙니다. 최종 평가 데이터는 학습이나 반복적인 설정 조정에 사용하
지 않습니다.

train.jsonl은 한 줄에 하나의 JSON 객체가 들어 있는 파일입니다. 첫 번째 레코드는 다음 구조입니다.

레코드
├── id             식별자
├── code_sha256    코드 해시
└── messages
    ├── system     모델이 따라야 할 역할·출력 규칙
    ├── user       분석할 코드·분석 범위 등 문제
    └── assistant  학습할 정답 JSON

id, code_sha256 같은 관리 정보와 모델에게 전달할 대화 내용은 구분해야 합니다. 파일에 있는 모든 필드를 모델에 넣는 것은 아닙니다.

우리의 정답은 단순히 “취약함/안전함”이라는 라벨 하나가 아닙니다. 실제 정답에는 다음 필드가 있습니다.

schema_version
scope
assessment
assessment_basis
findings
limitations
recommendations

즉, 판단뿐 아니라 근거와 출력 구조도 함께 학습하는 과제입니다.

### 직접 해볼 첫 실습

저장소 루트에서 환경을 활성화한 뒤 Python을 실행하세요.

source experiments/training-loop-debug/activate.sh
python

아래 코드를 직접 입력해보세요. 모델이나 GPU를 불러오지 않는 데이터 확인 실습입니다.

import json
from pathlib import Path

path = Path("data/processed/phase-f-source-v5-r1/train.jsonl")

with path.open(encoding="utf-8") as f:
    record = json.loads(next(f))

messages = record["messages"]
roles = [message["role"] for message in messages]

assert roles == ["system", "user", "assistant"]

# 모델에게 주는 문제
prompt_messages = messages[:-1]

# 모델이 출력하도록 학습할 정답
target_text = messages[-1]["content"]
target = json.loads(target_text)

print("대화 역할:", roles)
print("문제 메시지 수:", len(prompt_messages))
print("정답 필드:", sorted(target))
print("분석 범위:", target["scope"])
print("정답 판단:", target["assessment"])

현재 첫 번째 레코드에서는 다음 결과가 나옵니다.

대화 역할: ['system', 'user', 'assistant']
문제 메시지 수: 2
### 꼭 이해할 점: 학습할 때는 정답도 입력에 들어갑니다

조금 의외일 수 있지만, 일반적인 다음 토큰 예측 학습에서는 문제와 정답을 연결한 시퀀스를 모델에 넣습니다.

학습: system + user + 정답 assistant
추론: system + user → assistant를 모델이 생성

학습할 때 정답을 넣는 이유는, 앞부분이 주어졌을 때 다음 정답 토큰을 예측하도록 가르치기 위해서입니다. 정상적인 causal attention에서는 미래의
정답 토큰을 미리 볼 수 없습니다. 이 방식을 teacher forcing이라고 합니다.

우리 기존 학습 구현은 문제 부분을 읽게 하되, 정답 부분에 대해서만 loss를 계산하도록 구성되어 있습니다.

다음 단계에서 이 구분을 코드로 표현합니다.

- input_ids: 모델이 읽는 토큰 번호.
- attention_mask: 패딩 등 입력의 유효 위치를 구분하는 마스크.
- labels: 정답 토큰 번호와 loss 계산에서 제외할 위치(-100).

오늘은 “문제는 system/user, 목표 출력은 assistant JSON이며, 학습에서는 이들을 연결해 정답 부분을 예측한다”까지 이해하면 됩니다. 다음 실습은
지금 읽은 이 한 건을 위 세 배열로 바꾸고, 실제로 어느 위치에서 loss가 계산되는지 확인하는 것입니다.

## 2단계: 대화를 모델이 학습할 숫자로 바꾸기

### 1. 이번 단계의 목표

지난 단계에서는 데이터를 문제와 정답으로 나눴습니다.

문제: system + user
정답: assistant의 JSON 응답

하지만 모델은 문자열을 그대로 계산하지 않습니다. 먼저 토크나이저가 문자열을 토큰 번호의 배열로 변환합니다.

이번에 만들 데이터는 세 가지입니다.

이름              역할
━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
input_ids         모델이 읽는 토큰 번호
────────────────  ────────────────────────────────────────────────────
attention_mask    실제 입력과 패딩을 구분
────────────────  ────────────────────────────────────────────────────
labels            예측해야 할 정답 토큰과 loss 계산 제외 위치를 지정

### 2. 토크나이저와 채팅 템플릿

**토크나이저(tokenizer)**는 텍스트를 토큰으로 나누고 각 토큰을 번호로 변환합니다. 토큰 하나가 반드시 단어나 글자 하나에 대응하는 것은 아닙니
다.

**채팅 템플릿(chat template)**은 대화에 역할·경계·종료 표시 등을 붙여 모델이 기대하는 형식으로 만드는 규칙입니다.

messages
→ 채팅 템플릿 적용
→ 토큰화
→ input_ids

따라서 system, user, assistant의 내용만 단순히 이어 붙이면 안 됩니다. 학습과 추론 모두 같은 모델의 대화 형식을 사용해야 합니다.

### 3. attention_mask와 labels의 차이

다음은 설명용 가상 토큰 번호입니다.

영역              문제           정답        패딩
input_ids       [ 11,  12,     21,  22,      0 ]
attention_mask  [  1,   1,      1,   1,      0 ]
labels          [-100,-100,    21,  22,    -100 ]

여기서 중요한 점은 다음과 같습니다.

- 문제는 정답을 생성하는 데 필요하므로 모델이 읽어야 합니다.
- 하지만 이번 학습에서는 문제 자체를 예측하는 오차는 계산하지 않습니다.
- 정답 영역은 모델이 읽으면서 다음 토큰을 예측하도록 학습합니다.
- 패딩은 길이를 맞추기 위한 자리이므로 loss에서도 제외합니다.

-100은 토큰 번호가 아니라 loss 계산에서 해당 위치를 제외하라는 값입니다. input_ids가 아닌 labels에 넣습니다.

> attention_mask는 입력의 유효 위치를 구분하고, labels의 -100은 채점하지 않을 위치를 지정합니다. 둘은 역할이 다릅니다.

또한 미래 토큰을 보지 못하게 하는 causal mask는 별도입니다. attention_mask가 모두 1이어도 미래 정답을 볼 수 있다는 뜻은 아닙니다.

### 4. 직접 작성할 코드

현재 main.py의 main() 함수 안에서, 1단계 코드 뒤에 이어 작성하세요. 아래 코드는 함수 내부에 맞게 한 단계 들여써야 합니다.

#### 4.1. 토크나이저 준비

from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained(
    "adapters/source-v2-unsloth-v2/canary/final",
    local_files_only=True,
)

기존 adapter 디렉터리에 저장된 토크나이저 파일만 읽습니다. 모델이나 adapter 가중치는 불러오지 않으며, 다운로드도 하지 않습니다.

#### 4.2. 문제와 전체 대화를 각각 토큰화

training_messages = prompt_messages + [
    {
        "role": "assistant",
        "thinking": "",
        "content": target_text,
    }
]

prompt = tokenizer.apply_chat_template(
    prompt_messages,
    tokenize=True,
    add_generation_prompt=True,
    return_dict=True,
    reasoning_effort="low",
)

full = tokenizer.apply_chat_template(
    training_messages,
    tokenize=True,
    add_generation_prompt=False,
    return_dict=True,
    reasoning_effort="low",
)

두 번 변환하는 이유는 문제가 끝나고 정답이 시작되는 경계를 찾기 위해서입니다.

- prompt: 문제와 assistant 응답 시작 표시까지 포함합니다.
- full: 실제 정답과 종료 표시까지 포함합니다.
- add_generation_prompt=True: 모델이 응답을 시작할 위치를 템플릿에 표시합니다. 생성 자체를 실행하는 옵션은 아닙니다.

thinking=""과 reasoning_effort="low"는 현재 프로젝트의 GPT-OSS 대화 형식에 맞춘 설정입니다. 모든 모델에 공통으로 필요한 옵션은 아닙니다.

#### 4.3. labels 만들기

prompt_ids = prompt["input_ids"]
input_ids = full["input_ids"]
attention_mask = full["attention_mask"]

prompt_length = len(prompt_ids)

# 문제의 토큰 배열이 전체 대화의 앞부분과 정확히 일치해야 합니다.
assert input_ids[:prompt_length] == prompt_ids

# 문제 영역은 loss에서 제외하고, 정답 영역은 학습 대상으로 둡니다.
labels = [-100] * prompt_length + input_ids[prompt_length:]

핵심은 마지막 한 줄입니다.

labels = [-100] * prompt_length + input_ids[prompt_length:]

이를 풀어 쓰면 다음과 같습니다.

문제 길이만큼 -100을 만든다
+
정답 영역의 토큰 번호를 그대로 붙인다

문제와 전체 대화를 따로 토큰화했을 때 경계가 항상 일치한다고 가정하면 안 됩니다. 그래서 앞의 assert로 확인합니다.

#### 4.4. 결과 검증

assert len(input_ids) == len(attention_mask) == len(labels)
assert len(input_ids) <= 2048
assert all(value == -100 for value in labels[:prompt_length])
assert labels[prompt_length:] == input_ids[prompt_length:]
assert any(value != -100 for value in labels)

print("전체 토큰 수:", len(input_ids))
print("프롬프트 토큰 수:", prompt_length)
print("정답 영역 토큰 수:", sum(value != -100 for value in labels))
print("attention_mask 값:", sorted(set(attention_mask))))
print("마스킹 검증: 통과")

위 코드의 attention_mask 출력 줄은 닫는 괄호가 세 개가 되도록 다음과 같이 작성하세요.

print("attention_mask 값:", sorted(set(attention_mask)))

저장소 루트에서 실행합니다.

source experiments/training-loop-debug/activate.sh
python main.py

### 5. 예상 결과와 해석

현재 첫 번째 학습 샘플과 위 설정으로 직접 확인한 결과입니다.

전체 토큰 수: 680
프롬프트 토큰 수: 502
정답 영역 토큰 수: 178
attention_mask 값: [1]
마스킹 검증: 통과

즉, 다음과 같이 구성됩니다.

전체 680토큰
├── 프롬프트 502토큰: 읽지만 직접적인 loss 대상에서는 제외
└── 정답 영역 178토큰: 예측하도록 학습

정답 영역에는 JSON 본문뿐 아니라 템플릿의 제어·종료 토큰도 포함됩니다. 따라서 178은 JSON 본문만의 토큰 수가 아닙니다.

이번에는 샘플 하나를 패딩 없이 변환했으므로 attention_mask가 모두 1입니다.

### 6. 왜 labels에 입력 토큰을 그대로 복사할까?

“같은 위치의 토큰을 맞히면 정답을 이미 본 것 아닌가?”라는 의문이 들 수 있습니다.

다음 토큰 예측에서는 실제 비교 위치가 한 칸 어긋납니다.

모델이 읽은 내용         예측할 정답
문제                    정답 첫 토큰
문제 + 정답 첫 토큰      정답 두 번째 토큰
문제 + 정답 앞 두 토큰   정답 세 번째 토큰

일반적인 Hugging Face causal LM의 loss 구현은 이 위치 조정을 내부에서 수행합니다. 해당 구현을 사용할 때는 labels를 미리 한 칸 이동시키지 않
습니다. 직접 loss를 작성하는 단계에서 이 계산을 다시 확인하겠습니다.

### 7. 이번 단계의 완료 기준

다음 세 가지를 설명할 수 있으면 됩니다.

- input_ids에는 문제와 정답이 모두 들어간다.
- 문제 영역의 labels=-100은 문제를 숨기는 것이 아니라 loss에서 제외하는 것이다.
- 정답 토큰을 순서대로 예측하는 과정이 학습이며, 미래 정답은 보지 못해야 한다.