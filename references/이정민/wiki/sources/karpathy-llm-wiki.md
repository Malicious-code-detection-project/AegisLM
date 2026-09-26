---
type: Reference
title: Karpathy LLM Wiki — 출처 요약
description: 원자료와 연결된 지식을 분리하고 조회·반영·점검하는 아이디어.
status: draft
sources:
  - id: karpathy-copy
    resource: ../../raw/karpathy/llm-wiki.md
  - id: copy-provenance
    resource: ../../raw/karpathy/SOURCE.md
---

# Karpathy LLM Wiki

<a id="C-01"></a>
## 원자료와 재사용 지식

**출처 주장:** 원자료를 보존하고, 읽은 내용에서 연결된 Markdown 지식을 만들고 갱신하는 패턴이다. 매번 원자료에서 답을 다시 구성하는 흐름과 대비한다. 이 대비를 모든 RAG의 한계라는 일반 명제로 확대하지 않는다.[^karpathy-copy]

<a id="C-02"></a>
## 조회·반영·점검

원문의 `Operations`, `Indexing and logging`은 자료 반영, 관련 지식 조회, 충돌·낡은 내용·링크 점검을 제시한다. 인덱스는 탐색, 로그는 변경 이력이다. 실행 프로그램이나 모든 도구의 자동 동작을 제공하는 문서는 아니다.[^karpathy-copy]

<a id="C-03"></a>
## 적용과 한계

Astra 중심 분업·권한·독립 검토·과업 성공 기준은 [우리의 설계](../decisions/harness-wiki-integration.md)다. 원문 저자의 보증이나 실험 결과가 아니다.

v3에서는 v2.1에 포함된 사본을 보존했다. 공개 원문과 최신 바이트 대조를 새로 수행하지 않았으며, v2 당시 대조 기록과 사본의 한계는 출처 문서에 있다. 실제 검색 품질·재작업·시간 절감은 미검증이다.[^copy-provenance]

[^karpathy-copy]: [보존 본문](../../raw/karpathy/llm-wiki.md), `The core idea`, `Architecture`, `Operations`, `Indexing and logging`.
[^copy-provenance]: [사본의 직접 입력·변환·공개 대조 한계](../../raw/karpathy/SOURCE.md).
