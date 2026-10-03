# 모델 운영표 — 역할과 별도 관리

기본 프로필은 `openai-balanced`다. 아래는 **배정 제안**이며 계정·앱에서 실행 확인된 목록이 아니다. 모델 설명과 식별자는 2026-09-30 공식 자료에서 확인했고 [출처](../reference/cases.md)에 연결했다. 역할 문서는 모델과 무관하게 유지한다.

## 슬롯과 역할

| 역할 | 슬롯 | OpenAI 시작 추론값 |
| --- | --- | --- |
| 메인 | DEFAULT | medium |
| explorer | FAST | low |
| planner | DEFAULT; 중요한 난제만 DEEP | medium; DEEP high |
| patcher | DEFAULT | medium |
| reviewer | DEFAULT; 중요한 난제만 DEEP | medium; 고영향이면 high 검토 |
| tester | DEFAULT | medium |

FAST는 의무적으로 다른 모델을 쓰라는 뜻이 아니다. 위험·복잡도가 높으면 같은 모델의 강도를 높이거나 DEEP를 검토한다. `max`를 기본값으로 삼지 않는다. 업체마다 추론 옵션과 의미가 다르므로 위 값을 타사에 그대로 복사하지 않는다.

## 프로필 후보

| 프로필 | DEFAULT | FAST | DEEP |
| --- | --- | --- | --- |
| openai-balanced | `gpt-6.1-sol` | 동일 모델, low | `gpt-6-astra` |
| claude-only | `claude-sonnet-5-5` | 동일 모델; 검증 후 `claude-haiku-4-5-20251001` 선택 가능 | `claude-opus-5-5` |
| gemini-only | `gemini-3.8-flash` | 동일 모델 | 미지정; 검증된 후보가 생길 때 추가 |
| mixed | 승인·검증된 DEFAULT | 승인·검증된 FAST | 승인·검증된 Astra 또는 타사 후보 |

이는 **역할 대체 후보이지 모델 간 동급 성능표가 아니다**. Gemini의 이름에 Pro가 있다고 무조건 DEEP로 올리지 않는다. 로컬 모델도 필요한 도구·수정·검증 능력을 시험한 뒤 후보로 넣는다. 공급자별 실제 식별자는 실행 앱의 목록에서 확인한다.

OpenAI 모델의 추론값·API 조건은 [Sol 문서](https://developers.openai.com/api/docs/models/gpt-6.1-sol)와 [Astra 문서](https://developers.openai.com/api/docs/models/gpt-6-astra)를 따른다. Sol 6.1의 도구 호출에는 Responses API가 필요하다. Chat Completions만 연결한 앱을 동등한 실행 환경으로 보지 않는다. 타사 모델 ID는 [Claude](https://platform.claude.com/docs/en/models/overview), [Gemini](https://ai.google.dev/gemini-api/docs/models) 자료를 참고하되 실제 지원은 별도 확인한다.

## DEEP와 장애 처리

DEEP는 큰 재작업을 유발할 사전 결정, 근거를 모아도 풀리지 않는 난제, 중요한 결론의 추가 검토에만 사용한다. 질문·현재 후보·근거·반례·막힌 이유·기대 결정을 묶어 전달한다. 이미 끝낸 전체 과업을 다시 작성시키지 않는다. 연구 대부분이 어려운 판단이면 해당 과업의 메인을 DEEP로 시작할 수도 있다.

미지원·인증·도구 오류는 지능 부족과 다르다. 더 비싼 모델로 바꾸기 전에 연결 문제를 분리한다. 429/장애의 무한 재시도·무단 공급자 전환은 금지한다. 허용된 후보가 없으면 부분 결과와 필요한 연결을 보고한다. 필수 품질을 만족하지 못하는 모델로 조용히 낮추지 않는다.

프로필을 바꿀 때 `앱/버전 → 제공자/모델 ID → 요청·실제 추론값 → 도구·권한 → 전송 허용 → 확인 근거`를 과업에 한 번 기록한다. 공식 공개, 목록 노출, 도구 왕복 성공, 역할 수행 성공을 구분한다. 모르면 미확인으로 둔다. 단가·구독 한도·실제 과업 비용은 섞지 않는다. 검증 계획은 [EVALUATION.md](../EVALUATION.md)에 있다.
