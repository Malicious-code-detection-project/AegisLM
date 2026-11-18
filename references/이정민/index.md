# 이정민 · V3 Markdown 하네스

**Luna finds. Terra builds. Sol decides. Astra challenges.**

진입점: `references/이정민/index.md` · 버전: V3.1.1-MD · 2026-09-18

이 폴더는 선택된 개인의 **작업 규칙 문서**다. 팀 규칙·실제 도구 권한을 대체하지 않는다.
설치, 스크립트 실행, 전역 설정 변경 없이 사용한다. 폴더 전체를 한 번에 읽지 않는다.

## 가장 먼저

1. 사용자가 이번 작업에 이 하네스를 지정했는지 확인한다. 지정되지 않았다면 다른 사람의 작업 방식에 개입하지 않는다.
2. 실제 프로젝트와 변경 대상 경로에 적용되는 팀 규칙·사용자 요청을 확인한다. 충돌 시 개인 지시를 적용하지 않고 보고한다.
3. 하네스는 역할·작업 배분·인수인계·검증 방법을 정의한다. 작업 목표·현재 단계·실행 한도는
   최신 사용자 요청과 해당 작업 문서에서 확인하며 하네스에 고정하지 않는다.
   프로젝트 경로와 정본 위치는 [프로젝트 참고표](config/project.md)를 참고한다.
4. [모델 운영표](config/models.md)의 요청값과 현재 실행 환경의 실제 모델·권한을 구분한다.
   확인되지 않은 모델 사용·위임·검증을 수행했다고 기록하지 않는다.
5. Sol은 [Sol 역할](roles/sol.md)과 [작업 배분](harness/routing.md)을 읽는다.
   하위 작업자는 **자기 역할 + 적용 팀 규칙 + 작업 패킷 + [인수인계](harness/handoff.md)**를 기본으로 읽는다.

## 필요한 문서만 선택

| 현재 상황 | 읽을 문서 |
|---|---|
| 사람이 처음 사용 / 전체 폴더 구조 확인 | [시작 안내](START_HERE.md) |
| 운영 목적·책임 범위 확인 | [하네스 개요](harness/harness.md) |
| 모델 요청값 확인 | [모델 운영표](config/models.md) |
| 실행 방식·모델 확인에 어려움 | [세션 운영](harness/runtime.md) |
| 프로젝트 경로·검증 방법 확인 | [프로젝트 참고표](config/project.md), 실제 팀 정본 |
| 비단순 작업 조율 | [orchestrator 절차](skills/orchestrator/SKILL.md) |
| 고위험·반복 실패·감사 미수행 | [승격](harness/escalation.md) |
| 검증·독립 리뷰·수용 판단 | [검토 규칙](harness/review.md) |
| 구현 / 오류 수정 / 조사 | [구현](playbooks/implementation.md) / [디버깅](playbooks/debugging.md) / [조사](playbooks/research.md) 중 필요한 것 |
| 보안 / 설계 검토 | [보안 검토](playbooks/security-review.md) / [설계 검토](playbooks/architecture-review.md) |
| WSL·여러 작업자의 충돌 예방 | [협업](playbooks/wsl-collaboration.md) |
| 다른 팀원의 공식·작업법 활용 | [참고자료 목록](references.md) → 선택한 원본. 필요 시 [참조 규칙](harness/team-references.md) |

역할: [Sol](roles/sol.md) · [Terra](roles/terra.md) · [Luna](roles/luna.md) · [Astra](roles/astra.md).
양식은 복잡한 위임·검토에 필요한 만큼만 사용한다. 단순 작업마다 모든 문서를 읽거나 모든 양식을 만들지 않는다.

유지보수할 때만: [전환 안내](MIGRATION_V2_TO_V3.md) · [선택적 운영 평가](EVALUATION.md) · [변경 기록](log.md).
