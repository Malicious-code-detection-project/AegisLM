# Jeongmin · V3 Harness

**Luna finds. Terra builds. Sol decides. Astra challenges.**

이 폴더는 선택된 사용자의 개인 작업 방식이다. 팀의 공식 규칙이나 도구 권한을 대체하지 않는다.
폴더 전체를 읽지 말고, 아래 조건에 맞는 문서만 읽는다. 경로는 이 파일 기준이다.

## 세션 진입

1. 실행 환경의 지시 우선순위, 실제 루트/작업 경로의 `AGENTS.md`와 override, 팀 규칙을 확인한다.
2. 저장소 루트의 `.active-profile` 또는 사용자의 명시적 선택으로 이 프로필이 선택됐는지 확인한다.
3. 첫 세션에서는 [실행 연결](harness/runtime.md)을 읽고 실제 모델·권한·작업 디렉터리를 확인한다.
4. Sol은 [Sol 역할](roles/sol.md)과 [작업 배분](harness/routing.md)을 읽는다.
   하위 에이전트는 **자기 역할 파일 + [인수인계](harness/handoff.md) + 전달받은 작업**만 기본으로 읽는다.
5. 코드를 수정하기 전에 해당 코드 경로의 팀 규칙과 실제 프로젝트 명령을 추가 확인한다.

## 필요할 때만 읽기

| 조건 | 문서 |
|---|---|
| 하네스 구조·운영 목적 확인 | [harness.md](harness/harness.md) |
| 비단순 작업의 전체 조율 | [orchestrator](skills/orchestrator/SKILL.md) |
| 역할·위험·병렬화 결정 | [routing](harness/routing.md) |
| 보안·아키텍처·반복 실패·모델 부재 | [escalation](harness/escalation.md) |
| 작업 위임·결과 반환 | [handoff](harness/handoff.md) |
| 검증·독립 리뷰·최종 승인 | [review](harness/review.md) |
| 동료의 참고 공식/작업법 사용 | [참조 규칙](harness/team-references.md), [목록](references.md) |
| 기능 구현 / 디버깅 / 조사 | [implementation](playbooks/implementation.md), [debugging](playbooks/debugging.md), [research](playbooks/research.md) 중 하나 |
| 보안 / 설계 검토 | [security-review](playbooks/security-review.md), [architecture-review](playbooks/architecture-review.md) |
| WSL 병렬 작업·worktree | [wsl-collaboration](playbooks/wsl-collaboration.md) |

역할 문서: [Sol](roles/sol.md) · [Terra](roles/terra.md) · [Luna](roles/luna.md) · [Astra](roles/astra.md).
다른 사람의 `index.md`나 전체 하네스를 자동으로 이어 읽지 않는다.
공식 팀 규칙과 개인 문서가 충돌하면 개인 지시를 적용하지 않고 충돌을 보고한다.

## 유지보수할 때만

[V2→V3](MIGRATION_V2_TO_V3.md) · [평가 계획](EVALUATION.md) · [공식 출처](SOURCES.md) · [변경 기록](log.md).
