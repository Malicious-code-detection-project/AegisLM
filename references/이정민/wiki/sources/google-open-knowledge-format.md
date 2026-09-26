---
type: Reference
title: OKF 0.2 — 최소 표현과 확인 경계
description: 공식 필수 필드와 선택 신뢰 정보를 개인 Wiki 운영 기준과 구분.
status: draft
sources:
  - id: okf-spec
    resource: https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md
---

# OKF 적용 근거

**출처 확인:** 2026-09-20, 공식 저장소 `SPEC.md` 공개 본문은 버전 0.2였다. 특정 commit을 고정한 사본은 아니며 이후 개정은 재확인한다.[^okf-spec]

## 이번에 사용하는 범위

공식 사양의 개념 문서는 Markdown와 YAML frontmatter를 사용하고 필수 키는 `type`이다. `index.md`, `log.md`는 예약 이름이다. 루트 인덱스는 `okf_version`을 선언할 수 있고, 로그 날짜는 `YYYY-MM-DD` 형식이다. `sources` 항목을 쓰면 `resource`가 필요하고, 주장 각주는 `id`에 연결한다. 신뢰·수명 정보는 선택이다.[^okf-spec]

`generated`는 작성, `verified`는 확인 사건이며 시간 값에는 명시적 시간대가 필요하다. `status`는 `draft/stable/deprecated`이고 생략 기본값은 `stable`이다. 그래서 우리 새 페이지는 `draft`를 명시한다. 선택 필드를 만들지 않은 것은 검증됐다는 의미가 아니다.[^okf-spec]

폴더와 유형은 목적에 맞춰 정할 수 있다. `/` 경로는 번들 기준, 그 밖은 상대 경로로 사용할 수 있다. 새로운 런타임이나 전역 설정을 요구하는 형식은 아니다.[^okf-spec]

## 개인 운영과의 구분

우리 제목·설명·근거·적용 조건·편집 순서는 [지식 절차](../../harness/playbooks/llm-wiki.md)에서 정한다. 사양의 보편적 필수 요건으로 확대하지 않는다. `harness/`와 원자료는 지식 개념으로 바꾸지 않는다.

원자료 대조와 별개로 외부 OKF 소비 도구 호환성·사용자 환경 로딩은 시험하지 않았다. 정적 형식 검사를 사람 승인·별도 Sol 검토·attestation으로 표시하지 않으며 `verified`도 기입하지 않았다. 기존 사용자의 유효한 메타데이터는 이 최소 예시에 맞추려고 제거하지 않는다.

[^okf-spec]: 공식 SPEC.md §§3–9, 11–12. URL은 동일 ID의 `sources`에 있다. 사양 전문을 재배포하지 않는다.
