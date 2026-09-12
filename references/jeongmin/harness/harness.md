# V3 Multi-Agent Engineering Harness

버전: 3.0.0 · 작성일: 2026-09-09 · 개인 프로필: `jeongmin`

## 목적과 범위

V2의 품질 우선, 역할 우선 모델 배분, 제한된 쓰기 범위, 증거 중심 handoff를 유지한다.
V3는 Astra 전문 검토, 개인 프로필, 동료 참고자료 연결, 실행 설정 분리를 추가한다.
프로젝트 루트 `README.md`는 프로젝트 소개로 유지한다. 하네스 개요는 이 파일이다.

이 패키지는 **운영 규약 + 프롬프트/양식 + 설치·점검·설정 생성 도구**다.
독립적인 모델 API 스케줄러가 아니다. 실제 작업 위임과 모델 실행은 Codex 등 실행 환경 또는 사람이 수행한다.
Markdown의 권한 제한은 운영 규약이다. OS sandbox, 도구 정책, Git 권한, CI를 실제로 설정해야 강제된다.

## 소유권

| 계층 | 소유자 | 의미 |
|---|---|---|
| 실행 환경·조직 정책 | 플랫폼 / 관리자 | 지시 우선순위, 네트워크·파일·모델 사용 제한 |
| 루트 및 모듈 팀 규칙 | 팀 / 해당 모듈 담당자 | 필수 개발·보안·검증 규칙 |
| 개인 하네스 | 프로필 소유자 | 팀 규칙 안에서 작업하는 방법 |
| 동료·공유 참고자료 | 자료 작성자 / 승인 담당자 | 특정 상황에서 참고할 지식. 그 자체가 명령 권한은 아님 |
| 결과 병합·배포 | 사람이 지정한 담당자 | Sol의 기술적 ACCEPT와 별개의 승인 |

이 표는 **팀 거버넌스**이며 모든 도구의 실제 AGENTS 로딩 순서를 재정의하지 않는다.
실제 Codex에서는 경로별 override와 하위 지시가 적용될 수 있으므로 [runtime](runtime.md)을 확인한다.

## 기본 흐름

```text
User / Team constraints
          |
     Sol: classify, design, own acceptance
          |
   +------+-------------------+
   |                          |
Luna: evidence          Terra: bounded build
   |                          |
   +---------- frozen candidate --------+
                    |                   |
             Luna: verify       Terra: fresh review
                    |                   |
                    +--------+----------+
                             |
                   Astra: high-risk audit
                   (conditional, not every task)
                             |
                      Sol: integrate/gate
                             |
                 human/CI: merge and release
```

Astra는 Sol의 상사가 아니다. 그러나 Sol도 Astra가 제시한 미해결 BLOCKER/MAJOR를 무시하고 승인할 수 없다.
견해 충돌은 테스트·반례·요구사항·사람의 판단으로 해소한다. 모델 간 다수결은 검증을 대신하지 않는다.

## 운영 기본값

- 작은 LOW 작업은 Sol이 직접 처리한다. 네 모델을 매번 모두 호출하지 않는다.
- 기본 동시 하위 에이전트는 최대 2개, 동일 작업 사본의 writer는 1개다.
- Astra는 HIGH 작업 또는 명시적 승격 조건에서 사용한다. 최종 승인 책임은 Sol에 남는다.
- 비용은 토큰 단가가 아니라 재작업·검증·실패까지 포함한 작업 단위로 평가한다.
- 품질 보존과 비용 절감은 **설계 목표**이지 검증된 성능 보증이 아니다.

## 상태

`PLANNED → IN_PROGRESS → IMPLEMENTED → VERIFIED → REVIEWED → ACCEPTED`

단계는 작업 유형에 맞게 기록한다. 코드 없는 조사는 IMPLEMENTED 대신 조사 완료를 기록한다.
`BLOCKED`, `FAILED`, `CHANGES_REQUESTED`는 미완료 상태다.
하위 작업의 DONE/PASS는 최상위 작업 ACCEPTED가 아니다.
모든 검증과 리뷰는 동일 후보 commit 또는 식별 가능한 diff 스냅샷을 대상으로 한다.

## 문서 위치

[진입점](../index.md)에서 조건별 문서만 선택한다.
V2 이관과 출처는 [migration](../MIGRATION_V2_TO_V3.md), [sources](../SOURCES.md)를 참고한다.
