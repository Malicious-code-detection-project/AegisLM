# 이정민 개인 하네스 — v4

현재 공통 하네스는 [`harness/README.md`](harness/README.md)다.
2026-10-02에 AegisLM_Architecture의 v4를 이 저장소에 적용했다.

## 세션 진입

1. 저장소 루트의 `AGENTS.md`와 적용되는 경로별 팀 규칙을 확인한다.
2. `.active-profile`의 ASCII 프로필 ID `jeongmin`이 `references/이정민/`을 선택한다.
3. 메인은 [공통 원칙](harness/core/principles.md)과 현재 과업부터 읽고 직접 수행한다.
   구조·사용법이 필요할 때 하네스 README를 읽는다. 유효한 지침을 반복 로딩하지 않는다.
4. 필요한 전문 기능만 `explorer/planner/patcher/reviewer/tester` 문서로 확인한다.
   역할 문서를 읽었다고 별도 에이전트 호출이 필요한 것은 아니다.
5. 위임·중요 실험에는 [운영 절차](harness/core/workflow.md), 최초 모델/플랫폼 연결에는
   [모델 후보표](harness/core/models.md)와 [실행 연결](harness/adapters/runtime.md)을 확인한다.

메인 실행 모델·추론값은 사용자가 선택하고 실제 런타임에서 확인한 설정을 따른다.
모델 후보표의 DEFAULT/FAST/DEEP는 참고 배정이며 자동 전환 명령이 아니다.
모든 역할 순차 호출·고비용 모델 강제·별도 관리자 추가는 기본 흐름이 아니다.
하네스 문서는 팀 규칙·사용자 요청·실제 도구 권한을 대체하지 않는다.

## 교체와 보존

v3 역할 문서, v3 skill router, 예전 로컬 에이전트 TOML 및 생성 설정을 정리했다.
공통 하네스와 과업 템플릿만 가져왔으며 Architecture의 연구 과업은 가져오지 않았다.
이 저장소의 원자료·기존 과업은 유지한다. Wiki의 현행 역할 설명은 v4와 맞췄다.
교체 전 사본·해시·파일 목록은 Git 제외 경로
`outputs/harness-migration-20261002/`에 보관한다.
실제 이관 범위와 검증은 [전환 기록](harness/REFACTOR.md)의 AegisLM 적용 절을 따른다.
