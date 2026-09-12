# 출처와 적용 범위

확인일: **2026-09-09**. 실제 설치 버전·계정·관리자 정책과 공식 문서를 다시 대조한다.
이 파일은 근거와 버전 확인용이며 매 작업에 전체 로딩할 필요는 없다.

## 이전 사용자 자료

사용자가 이전에 만든 V2/V2.1 하네스의 Library 파일: `AGENTS.md`, `harness.md`, `routing.md`,
`handoff.md`, `review.md`, `.agents/skills/orchestrator/SKILL.md`에 해당하는 `SKILL.md`.
확인한 내용은 품질 우선, role-first, Sol 최종 기술 책임, 제한된 쓰기, 독립 검토,
구조화된 handoff, README 보존이다. V3는 이 규칙을 개인 프로필 구조로 재작성하고 Astra를 추가했다.
Library 파일 자체에 원 저장소 commit 정보가 없어 특정 commit의 자동 migration으로 표현하지 않는다.

## 공식 런타임 문서

**S1. OpenAI — AGENTS.md configuration**
https://learn.chatgpt.com/docs/agent-configuration/agents-md

전역 및 프로젝트 경로별 지시 탐색, `AGENTS.override.md`, 계층 결합을 확인한 근거다.
루트 AGENTS가 언제나 어떤 지시보다 우선한다는 식으로 단순화하지 않았다.

**S2. OpenAI — Subagents / custom agents**
https://learn.chatgpt.com/docs/agent-configuration/subagents

`gpt-5.6`, `gpt-5.6-terra`, `gpt-5.6-luna` 후보와 `.codex/agents/*.toml` custom-agent 형식을
확인했다. `name`, `description`, `developer_instructions` 및 모델·reasoning·sandbox 설정의 근거다.
부모의 live 권한 override와 실제 child 권한 확인이 필요하다. 사용자 계정의 접근성은 별도다.

**S3. OpenAI — Build skills**
https://learn.chatgpt.com/docs/build-skills

`SKILL.md`의 name/description, progressive disclosure, `.agents/skills`의 탐색과
`agents/openai.yaml`의 `allow_implicit_invocation` 설정을 확인한 근거다.

**S4. OpenAI — Developer commands / CLI**
https://learn.chatgpt.com/docs/developer-commands?surface=cli

CLI model/sandbox/approval 선택 예시와 상태 확인 절차의 근거다.

**S5. OpenAI — Agent approvals and security**
https://learn.chatgpt.com/docs/agent-approvals-security

승인·sandbox가 실행 권한을 통제한다는 근거다. 개인 Markdown이나 role 명칭은 접근제어가 아니다.

**S6. OpenAI — Latest model guide**
https://developers.openai.com/api/docs/guides/latest-model

Astra의 문서상 API model ID `gpt-6-astra`를 확인했다. 이 ID의 API 문서 존재가 특정 Codex
버전/사용자 계정에서의 지원을 입증하지 않는다. local 설정은 unverified로 시작한다.

## V3에서 설계한 것

4개 역할 배치, LOW/MEDIUM/HIGH gate, 기본 동시 하위 작업 2개, worktree별 writer 1개,
동일 원인 실패 2회 후 재분류, 초기 reference 1–3개 선택은 **이 패키지의 운영 기본값**이다.
벤치마크로 입증된 최적값이나 공식 서비스 정책이 아니다. 프로젝트 위험·측정 결과로 조정한다.

실제 팀원 자료는 아직 받지 않았다. 참고 registry는 비워 두었고, 예시 경로를 활성 근거로 만들지 않았다.
성능·비용·지연·취약점 탐지율 개선 수치는 만들어 넣지 않았다.
