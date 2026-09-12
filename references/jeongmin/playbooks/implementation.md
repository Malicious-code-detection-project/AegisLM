# Playbook · Implementation

조건: 기능 추가·동작 수정·리팩터링. [routing](../harness/routing.md)이 우선이다.

Sol은 요구사항·불변 조건·영향 범위·risk·완료 조건을 정의한다.
모듈을 모르면 Luna에게 경로 조사만 맡긴다. 이미 안다면 중복 조사를 생략한다.
API/데이터 계약과 write scope를 확정한 뒤 Terra Builder에 작업을 전달한다.
HIGH 설계는 변경 전 Astra에게 경계와 반례를 검토하게 한다.

Terra는 기존 동작을 보존하는 최소 변경과 의미 있는 테스트를 작성한다.
새 의존성/공개 API 변경/범위 확대는 Sol의 결정 없이 진행하지 않는다.
완료되면 후보를 고정하고 Luna 검증, fresh Terra 리뷰를 위험에 맞게 수행한다.
HIGH는 최종 후보에 대한 Astra 감사까지 연결한다.

동료 참고자료는 `references.md`에서 현재 언어·버전·목적에 맞는 것만 선택한다.
권고 사항을 팀의 필수 규칙처럼 확대 해석하지 않는다.
최종 결과: 변경 파일 + 계약 충족 + 실제 검증 + finding 처리 + 수용 상태.
