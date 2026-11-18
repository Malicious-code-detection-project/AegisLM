---
type: Setup Guide
title: AegisLM V3.1.1-MD 운영 하네스
description: AegisLM 프로젝트의 역할·작업 배분·인수인계·검증 방법을 안내하는 하네스 진입점
tags: [aegislm, harness]
timestamp: 2026-09-18
status: active
---

# Scope

V3.1.1-MD는 AegisLM 프로젝트에서 에이전트가 협업하는 운영 방법을 정의한다.
작업 목표·현재 단계·대상 모델·실행 한도·완료 조건은 최신 사용자 요청과 해당 작업 문서에서 관리한다.
하네스에 이를 고정하거나 지난 작업의 조건을 다음 작업에 자동 적용하지 않는다.

정본 출처는 wiki의 `references/이정민/`이며, 로컬·서버에서
[프로젝트 snapshot](../references/이정민/index.md)을 함께 사용한다.
프로젝트 팀 규칙·최신 사용자 지시·실제 도구 권한을 확인한다.

# Roles and Evidence

- Director: 범위·계약·통합을 담당한다. 역할 이름이 실제 모델 교체를 뜻하지 않는다.
- Luna Scout/Verifier: 조사 또는 고정 후보 실행 검증.
- Terra Builder/Reviewer: 제한된 구현 또는 작성자와 다른 새 세션의 독립 리뷰.
- Astra: 필요한 난제 검토와 고위험 감사.
- 기본 하위 작업 최대 2개, worker 재위임 금지, 작업 사본당 writer 1개.
- 모델 실제 배정, 후보 hash, 명령·exit code, 결과·미검증을 구분해서 기록한다.
- MEDIUM 변경은 실행 검증·fresh review·통합 판단을 모두 확인한다.

# Task Context

[프로젝트 문서 인덱스](README.md)에서 현재 요청과 관련된 정본을 찾아 읽는다.
필요한 목표와 제약은 [작업 패킷](../references/이정민/templates/task.md)에 전달한다.
실제 진행 상태와 결과는 해당 작업 문서에 갱신한다.
