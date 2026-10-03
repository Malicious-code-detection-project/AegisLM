---
type: Decision
title: 과업 성공 중심 통합 구조
description: 기능별 역할과 교체 가능한 모델을 분리하고 과업·지식의 중복을 줄이는 설계 결정.
status: draft
sources:
  - id: harness-goal
    resource: ../../harness/core/principles.md
  - id: refactor
    resource: ../../harness/REFACTOR.md
---

# 통합 결정

<a id="C-01"></a>
## 공동 과업 성공

메인은 목표·작업 선택·결과 통합을 담당한다. explorer/planner/patcher/reviewer/tester는 필요한 전문 기능이다. 모델은 역할과 분리하여 배정한다. 모든 과업에서 다섯 역할을 호출하지 않으며 직함이나 모델 간 동의로 성공을 판정하지 않는다.[^harness-goal]

<a id="C-02"></a>
## 기록과 재사용 지식

현재 상태는 과업에, 재사용 결론은 Wiki에, 원자료는 원래 위치에 둔다. 새 과업은 `task.md` 하나로 시작한다. 기존 다섯 파일 과업은 변환하지 않고 이어간다. 기록 편집자는 메인 또는 지정된 한 명이다.[^refactor]

<a id="C-03"></a>
## 규칙을 한곳에

v3에서 통합한 [지식 운영 절차](../../harness/playbooks/llm-wiki.md)를 유지한다. v4는 역할/모델 배정을 분리하고 타사 대체도 같은 성공 기준으로 평가한다. 정책·템플릿·공개 사례 조사 전체를 기본 입력에 넣지 않는다.[^refactor]

<a id="C-04"></a>
## OKF 범위

OKF는 Wiki의 표현 형식에만 적용한다. 기존 0.2 운영 범위를 유지했으며 이번에 새 사양 인증을 수행한 것은 아니다. 출처·조건·확인 범위는 유지하고, 사용하지 않는 필드나 별도 기록 원장을 늘리지 않는다.[^refactor]

## 효과와 재검토

이 결정은 사용자 요청에 맞춘 설계다. v4는 역할 문서·연결 기준을 재작성했지만 실제 모델의 품질·시간·비용 개선은 미검증이다. 누락·권한 위반·불필요한 재작업이 생기면 영향받는 역할/배정/검증을 조정한다. 과거 원문은 이전 ZIP에 보존된다.

[^harness-goal]: [공통 원칙](../../harness/core/principles.md).
[^refactor]: [전환·측정·검증](../../harness/REFACTOR.md).
