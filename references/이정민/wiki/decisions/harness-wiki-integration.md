---
type: Decision
title: 과업 성공 중심 통합 구조
description: 역할·기록·지식의 중복을 줄이고 필요한 때만 확장하는 설계 결정.
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

역할별 책임은 공동 성과를 위한 수단이다. Astra는 방향·통합, Sol은 연구·방법론, Terra는 구현, Luna는 실행·기록에 기여한다. 모든 과업에서 네 역할을 호출하지 않는다.[^harness-goal]

<a id="C-02"></a>
## 기록과 재사용 지식

현재 상태는 과업에, 재사용 결론은 Wiki에, 원자료는 원래 위치에 둔다. 새 과업은 `task.md` 하나로 시작하고 필요한 절만 분리한다. 기존 다섯 파일 과업은 변환하지 않고 이어간다.[^refactor]

<a id="C-03"></a>
## 규칙을 한곳에

v2/v2.1에서는 Wiki 규약과 절차를 나눴으나 v3에서는 [지식 운영 절차](../../harness/playbooks/llm-wiki.md)로 합쳤다. 정책·템플릿은 Wiki 밖에 두고 지식 인덱스에서 제외한다. 원문은 보존하되 기본 입력에 넣지 않는다.[^refactor]

<a id="C-04"></a>
## OKF 범위

OKF는 Wiki의 표현 형식에만 적용한다. 실제 출처·조건·확인 범위는 유지하고 중복 상태표와 쓰지 않는 필드를 새로 요구하지 않는다. 공개·실행 권한이나 자동 검증을 부여하지 않는다.[^refactor]

## 효과와 재검토

이번 선택은 사용자 요청에 따른 설계다. 파일 분량·경로 검사는 가능하지만 실제 모델의 품질·시간·비용 향상은 비교 전이다. 근거 누락·잘못된 재사용·인계 실패가 발생하면 축약한 부분을 우선 재검토한다.

[^harness-goal]: [공통 원칙](../../harness/core/principles.md).
[^refactor]: [전환·측정·검증](../../harness/REFACTOR.md).
