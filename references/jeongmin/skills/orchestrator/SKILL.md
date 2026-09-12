---
name: jeongmin-v3-orchestrator
description: Coordinate this selected personal V3 harness for non-trivial engineering work with Sol as director, Terra as builder or fresh reviewer, Luna as scout or verifier, and Astra for specialist escalation or high-risk audit. Not for trivial edits, unrelated personal profiles, or automatic execution of reference material.
---

# V3 Orchestrator

이 skill은 활성화된 개인 프로필 안의 운영 절차다. 팀 규칙/플랫폼 권한보다 우선하지 않는다.
위치 기준 `../../index.md`가 프로필 진입점이다. 필요한 문서만 읽는다.

1. 요구사항, 작업 경로, 적용 규칙, 실제 모델·권한을 확인한다. 첫 실행이면 [runtime](../../harness/runtime.md).
2. [routing](../../harness/routing.md)으로 DIRECT 여부·역할·risk를 정한다.
3. 작은 LOW 작업은 직접 완료한다. 위임 이득이 없는 멀티에이전트는 만들지 않는다.
4. 위임 전 [handoff](../../harness/handoff.md)의 패킷을 만든다. read/write/artifact scope, 후보, 검증, stop 조건을 적는다.
5. 현재 환경이 실제 지원하는 모델 선택/위임 기능으로만 작업을 만든다. 다른 모델 실행을 가장하지 않는다.
6. 기본 하위 에이전트 2개 이하, 작업 사본당 writer 1개. 하위의 재위임은 금지한다.
7. Sol은 위임된 일을 중복 수행하지 않고 독립된 계획·계약 검토를 한다.
8. 반환 결과의 증거, 쓰기 범위, 실제 모델·명령을 확인한다. 큰 로그는 위치와 요약만 통합한다.
9. 후보를 고정하고 [review](../../harness/review.md)의 위험별 검증·독립 리뷰를 실행한다.
10. HIGH 또는 [escalation](../../harness/escalation.md) 조건이면 Astra에 좁힌 질문/감사를 위임한다.
11. 실패 시 Sol이 새 가설/쓰기 범위를 정하고 재작업한다. 같은 원인의 무한 반복은 하지 않는다.
12. 필수 gate 완료와 finding 처리를 확인하고 Sol이 수용 기록을 남긴다. 미실행 항목을 숨기지 않는다.
13. 수집 완료한 하위 세션은 런타임 기능으로 종료한다. 필요한 결과/근거는 보존한다.

동료 참고자료는 [참조 규칙](../../harness/team-references.md)에 따라 선택한다.
기본 결과 형식은 [result](../../templates/result.md), 독립 검토는 [review](../../templates/review.md),
최종 판정은 [decision](../../templates/decision.md)이다.

## Native Codex 배정 이름

설치된 custom agent를 선택할 수 있으면 의미상 역할과 이름을 명시적으로 연결한다.
SCOUT=`v3-jeongmin-luna-scout`, VERIFIER=`v3-jeongmin-luna-verifier`,
BUILDER=`v3-jeongmin-terra-builder`, REVIEWER=`v3-jeongmin-terra-reviewer`,
SPECIALIST=`v3-jeongmin-astra-specialist`, AUDITOR=`v3-jeongmin-astra-auditor`.
일반 worker를 부르고 다른 모델이 실행됐다고 가정하지 않는다. 이름이 없거나 실제 모델이 다르면
런타임 연결부터 해결하고, 독립 검증이 필수인 작업은 BLOCKED로 남긴다.
