# Handoff · V2 호환 필드 + V3 실행 증거

## 작업 패킷

V2의 9개 필드를 유지한다. 실제 작업에서는 [task 양식](../templates/task.md)을 복사해 채운다.

| 필드 | 내용 |
|---|---|
| TASK | 고유 task ID와 구체적 작업 |
| ROLE | SCOUT / BUILDER / VERIFIER / REVIEWER / SPECIALIST / AUDITOR |
| OBJECTIVE | 관찰 가능한 결과 |
| SCOPE | 읽을 모듈·파일·심볼 |
| WRITE SCOPE | 정확한 파일/디렉터리 허용 목록. 읽기 전용이면 none |
| CONTEXT | 요구사항·필수 계약·관측 사실·선택한 reference |
| CONSTRAINTS | API 유지, 네트워크/비밀정보/실행 제한, 하위 위임 금지 |
| DONE WHEN | 테스트·반례·산출물 등 판정 조건 |
| RETURN | 반드시 포함할 결과와 증거 |

V3 추가 필드: RISK, PROFILE, MODEL_SLOT, MODEL_REQUESTED, MODEL_ACTUAL,
BASE_REVISION, CANDIDATE, WORKTREE, ARTIFACT SCOPE, VALIDATION PLAN,
REFERENCE SNAPSHOTS, DEPENDENCIES, BUDGET/STOP, HUMAN APPROVAL.
미리 알 수 없는 MODEL_ACTUAL은 `unknown`으로 시작하고 런타임 증거로 갱신한다.
모델 자신의 '나는 Astra다'라는 대답만으로 actual model을 확정하지 않는다.

## 결과 패킷

표준: [result 양식](../templates/result.md)
검토: [review 양식](../templates/review.md)
최종 승인: [decision 양식](../templates/decision.md)

SCOUT/BUILDER/SPECIALIST: DONE | BLOCKED | FAILED.
VERIFIER: PASS | FAIL | BLOCKED. 개별 명령은 PASS | FAIL | NOT_RUN | BLOCKED.
REVIEWER/AUDITOR: PASS | CHANGES_REQUESTED | BLOCKED.

항상 SUMMARY, CHANGES, EVIDENCE, VALIDATION, RISKS, CONFIDENCE, ESCALATION을 포함한다.
검토에는 FINDINGS를 추가한다. 모델, 세션, 작업 사본, 후보 식별자를 남긴다.
리뷰의 PASS는 검토 범위 내 중대 결함을 발견하지 못했다는 뜻이지 무결함 보증이 아니다.

## 증거의 단위

- 소스: repo 기준 경로, 심볼, 필요 시 라인, commit/diff 식별자.
- 명령: 실제 argv 또는 실행 문자열, cwd, 종료 코드, 핵심 결과, 로그 위치, 실행 환경.
- 비커밋 변경: base SHA + patch의 SHA-256 + 새 파일들의 SHA-256 등 재식별 가능한 스냅샷.
- 문헌/동료 자료: source_path/URL, 문서 버전 또는 hash, 확인 날짜, 적용 범위.

관찰한 결과와 예상 결과를 분리한다. 실행하지 않은 명령은 계획에만 두거나 NOT_RUN으로 표시한다.
시험 캐시/리포트는 CHANGES의 source 변경과 구별해 ARTIFACTS에 기록한다.
큰 로그는 전체 반환하지 않고 위치·핵심 오류·요약을 반환한다. 비밀정보는 로그와 전달문 모두에서 제외한다.

## 독립성과 컨텍스트

Reviewer/Auditor에는 원 요구사항, 고정 후보, 관련 코드, 팀 규칙, 테스트 결과를 준다.
작성자의 장황한 정당화나 '문제없다'는 결론으로 검토를 유도하지 않는다.
필수 설계 제약과 인터페이스 계약은 생략하지 않는다.
새 세션의 동일 모델도 별도 검토는 가능하지만 오류가 통계적으로 독립이라고 주장하지 않는다.
개인적인 내부 사고과정 전문 대신 결론·근거·짧은 판단 이유를 반환한다.

## 신뢰도

HIGH: 핵심 범위를 확인했고 직접 증거와 검증이 일치한다.
MEDIUM: 핵심 주장은 지지되지만 비핵심 공백이 남는다.
LOW: 핵심 계약·증거·검증이 빠졌다. 추가 조사나 승격을 요청한다.
신뢰도 숫자나 모델 명성이 필수 검증을 대체할 수 없다.
