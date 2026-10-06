# 공개 사례 조사와 적용 근거

조회일: **2026-09-30**. 저장소 본문·역할 예제·공식 제품 문서를 읽었다. 공개 하네스를 설치하거나 모델을 실행하지 않았다. 브랜치/웹 문서는 가변 자료이며 commit 고정 스냅샷이라고 주장하지 않는다. 사용자가 제시한 다섯 역할 문장의 원 출처를 특정한 것은 아니다. 아래는 구조가 유사한 실제 구현이다.

문서·프롬프트의 전문 복사는 하지 않고, 공개 구조를 참고해 우리 규약을 새로 작성했다. 원본의 모델명·도구명·인증·성능 주장을 그대로 이전하지 않는다. 기존 카파시 원문은 사용자가 제공한 v3 사본의 바이트만 보존한다.

## 1. Pi 공식 subagent 예제 — 가장 직접적인 역할 참고

[README](https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/examples/extensions/subagent/README.md)는 별도 프로세스의 scout/planner/reviewer/worker와 사용량 표시, 연쇄·병렬 흐름을 공개한다. 예제 확장 코드가 있어야 동작하며 Markdown만 배치하는 것으로 실행되지 않는다.

[scout](https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/examples/extensions/subagent/agents/scout.md)는 Haiku를 지정하고 관련 구간·연결 관계를 다음 작업에 전달한다. [planner](https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/examples/extensions/subagent/agents/planner.md)와 [reviewer](https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/examples/extensions/subagent/agents/reviewer.md)는 Sonnet 예제를 사용하며, reviewer는 셸도 읽기 용도로 제한한다. [worker](https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/examples/extensions/subagent/agents/worker.md)는 범용 실행자다.

우리 적용: scout → explorer, planner/reviewer 유지, worker의 변경 업무 → patcher, 실행 진단 → tester. 원본의 넓은 worker 권한은 복사하지 않는다. Haiku/Sonnet은 예제의 배정이지 지금 과업의 최적 모델이라는 근거가 아니다. 우리 기본은 Sol 6.1, 타사-only 프로필은 역할별 검증 후 채택한다.

## 2. Oh My OpenCode Slim — 역할과 모델 프리셋 분리

[저장소](https://github.com/alvinunreal/oh-my-opencode-slim)는 역할별 모델 프리셋·혼합 제공자 구성을 공개한다. [작성자 프리셋](https://github.com/alvinunreal/oh-my-opencode-slim/blob/master/docs/authors-preset.md)은 작성자가 실제 사용하는 구성이라고 설명하는 자료다. 설정 공개와 성능 검증은 다르다.

[explorer 구현](https://github.com/alvinunreal/oh-my-opencode-slim/blob/master/src/agents/explorer.ts)은 역할 정의와 모델 인자를 따로 받는다. [orchestrator](https://github.com/alvinunreal/oh-my-opencode-slim/blob/master/src/agents/orchestrator.ts)는 작업 분리·검증 담당·쓰기 범위·결과 통합을 명시한다.

우리 적용: 역할 명세와 `core/models.md` 분리, 메인의 검증 책임, 제한된 전달 패킷. 원본의 강한 기본 위임·UI 전용 역할·다중 모델 Council·부가 서비스는 채택하지 않는다. 역할이 있다는 이유로 호출하지 않는 우리 비용 경계를 우선한다. 원본 프리셋도 오래될 수 있다고 명시하므로 모델 목록을 그대로 사용하지 않는다.

## 3. Oh My Pi — 모델 슬롯과 실행 도구의 분리

[공개 README](https://github.com/can1357/oh-my-pi)는 작업별 모델 슬롯, 하위 작업, 구조화된 반환, 별도 advisor를 설명한다. advisor가 매 턴을 확인하는 방식도 소개되어 있다.

우리 적용: DEFAULT/FAST/DEEP라는 간단한 슬롯과 역할별 반환 형식. 상시 advisor, 자동 기억 시스템, 추가 도구 설치는 도입하지 않는다. README의 성능·편집 효율 수치는 우리 과업에서 재현하지 않았고 본 패키지의 효과로 사용하지 않는다.

## 4. 사용자 공개 사례 — Major Hayden의 모델 프리셋

[사용기](https://major.io/p/opencode-model-presets-direnv/)는 OpenCode Slim에서 프로젝트별 프리셋을 사용하는 방법과 Anthropic/Vertex 후보 배열을 공개한다. 작성자 본인의 구성 설명이며 독립 벤치마크는 아니다.

우리 적용: 제공자별 프로필과 명시적인 대체 후보. direnv·환경 자동 변경·fallback 배열은 배포하지 않는다. 승인되지 않은 제공자로의 자동 데이터 전송이나 인증 우회도 도입하지 않는다.

## 공식 연결 근거

| 자료 | 이번에 확인한 내용 | 우리 반영 |
| --- | --- | --- |
| [OpenAI subagents](https://developers.openai.com/codex/subagents/) | 사용자 지정 에이전트·모델/추론값·상속·권한과 등록 방식 | 실제 자식 세션 설정 확인, Markdown 배치와 등록을 구분 |
| [OpenCode agents](https://opencode.ai/docs/agents/) | 역할별 모델, 제공자/모델 식별자, permission, 모델 미설정 시 상속 | 역할별 모델 연결·권한 확인, 공통 도구 이름을 강요하지 않음 |
| [OpenCode providers](https://opencode.ai/docs/providers/) | 여러 제공자를 연결하는 방법 | 지원 목록·공식 인증 경로를 실제 앱에서 확인 |
| [Claude Code subagents](https://code.claude.com/docs/en/sub-agents) | 역할별 문서·도구·모델 선택과 상속/대체 조건 | 타사-only 실행 프로필, 실제 모델 표시 확인 |

연결 문서와 프리셋은 역할에 맞춘 구조를 참고하는 근거다. 특정 모델의 우월성·계정 접근권·구독 전용 가능성·완전한 권한 강제를 보증하지 않는다.

## 공식 모델 식별자 확인

| 자료 | 공개 문서에서 확인 | 한계 |
| --- | --- | --- |
| [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) | `gpt-6.1-sol`; low/medium/high/xhigh/max; 도구 호출은 Responses API | 사용자 앱·계정에서는 미실행 |
| [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) | `gpt-6-astra`; 추론값 low~max | 선택적 난제 배정은 우리의 설계 가설 |
| [Claude 모델](https://platform.claude.com/docs/en/models/overview) | `claude-sonnet-5-5`, `claude-opus-5-5`, `claude-haiku-4-5-20251001` | DEFAULT/DEEP/FAST 배정의 동급 성능을 입증하지 않음 |
| [Gemini 모델](https://ai.google.dev/gemini-api/docs/models) | `gemini-3.8-flash` | 별도 DEEP 모델을 자동 지정하지 않음 |

문서에 공개된 식별자를 API 원형으로 기록했다. OpenCode 등에서 제공자 prefix가 붙을 수 있으나 실제 앱 목록에 없는 조합을 만들어 넣지 않는다. 추론 옵션은 모델/제공자별로 재확인한다. 가격표는 패키지에 복제하지 않는다. 계정의 실제 사용량·과금과 성공한 전체 과업 비용으로 비교한다.

## 채택·변경·제외의 요약

채택: 기능별 역할, 짧은 근거 전달, 역할과 모델 분리, 원본을 보는 검토, 실제 설정 확인.
변경: 비용 절감을 위해 Sol 6.1 기본; 고난도만 Astra; tester를 verify/repair로 나눔; 연구 설계·평가 보호를 역할에 유지.
제외: 무조건 다섯 단계, 상시 고비용 advisor, 일괄 설치, 재귀 위임, 다수결 검증, 공개 프리셋의 무검증 복사.

이 역할 대응은 같은 일을 맡길 후보를 정하는 설계다. 프롬프트만으로 모델의 부족한 능력을 보장할 수 없으므로 [실운영 비교](../EVALUATION.md)를 통과시켜야 한다.
