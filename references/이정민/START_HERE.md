# V3.1.1 Markdown 전용 하네스 · 이정민

**프로젝트의 `references/이정민/`에 두고 `index.md`부터 읽게 하면 된다.**

설치·실행 스크립트 없이 쓰는 개인 하네스다. 기존 역할·위험별 검증·참고자료 연결 구조는 유지했다.
하네스에는 역할·작업 배분·인수인계·검증 방법을 둔다. 작업 목표와 현재 상태는
최신 사용자 요청과 해당 작업 문서에서 확인한다.

## 적용

1. 압축을 별도 위치에 푼 뒤 그 안의 `references/이정민/` 폴더를 프로젝트의 같은 위치에 둔다.
   이미 같은 폴더에 문서가 있으면 내용을 비교한 후 필요한 파일만 교체한다.
2. 아래 시작 요청과 이번 작업을 에이전트에 전달한다.
3. 현재 작업에 필요한 문서만 읽고 기존 프로젝트 환경에서 진행한다.

```text
references/이정민/index.md를 개인 하네스 진입점으로 사용해라.
팀 규칙을 우선하고 이번 작업에 필요한 문서만 읽어라.
최신 사용자 요청과 관련 작업 문서에서 범위·제약·완료 조건을 확인해라.

이번 작업: <실제 요청>
```

상세 시작 문구는 [templates/session-start.md](templates/session-start.md)에 있다.
기본 적용에는 루트 README·AGENTS·기존 도구 설정·팀 공용 폴더를 수정할 필요가 없다.
다만 사용자가 명시적으로 승인한 governance upgrade는 정확한 WRITE SCOPE의 문서에 한해
가능하며, native `.codex` 설정은 변경하지 않는다.
폴더를 두는 것만으로 자동 실행/자동 모델 전환이 생기는 것은 아니므로 위처럼 진입점을 지정한다.

## 역할과 요청값

| 모델 | 역할 | 요청 추론 강도 |
|---|---|---|
| Sol | 설계·조율·통합·기술 수용 | high |
| Terra | 구현 / 새 세션 독립 리뷰 | high |
| Luna | 조사 / 실행 검증 | low |
| Astra | 고난도 전문 판단 / 독립 감사 | high |

사용자가 마지막으로 지정한 model ID와 강도는 [config/models.md](config/models.md)에 반영했다.
Markdown에 적힌 요청값과 실제 실행 환경의 모델 설정은 별개다.
현재 도구에 이미 있는 기능을 사용하고, 실제 지원·확인이 안 된 위임을 수행했다고 표시하지 않는다.
모든 작업에 네 모델을 호출하지 않는다. 작은 작업은 직접, 고위험·난제에만 Astra를 투입한다.

## 파일 구조

```text
references/
└── 이정민/
    ├── config/
    │   ├── models.md
    │   └── project.md
    ├── harness/
    │   ├── escalation.md
    │   ├── handoff.md
    │   ├── harness.md
    │   ├── review.md
    │   ├── routing.md
    │   ├── runtime.md
    │   └── team-references.md
    ├── playbooks/
    │   ├── architecture-review.md
    │   ├── debugging.md
    │   ├── implementation.md
    │   ├── research.md
    │   ├── security-review.md
    │   └── wsl-collaboration.md
    ├── roles/
    │   ├── astra.md
    │   ├── luna.md
    │   ├── sol.md
    │   └── terra.md
    ├── skills/
    │   └── orchestrator/
    │       └── SKILL.md
    ├── templates/
    │   ├── decision.md
    │   ├── reference.md
    │   ├── result.md
    │   ├── review.md
    │   ├── session-start.md
    │   └── task.md
    ├── EVALUATION.md
    ├── index.md
    ├── log.md
    ├── MIGRATION_V2_TO_V3.md
    ├── references.md
    └── START_HERE.md
```

## 폴더별 사용

`index.md`는 진입점, `harness/`는 배분·인계·검증 규칙, `roles/`는 담당 역할이다.
`config/`의 두 문서는 실행 설정이 아니라 사람이 읽고 에이전트가 참고하는 운영표다.
`playbooks/`는 필요한 업무 절차 하나를 선택하는 곳이고, `templates/`는 복잡한 위임·검토에 쓸 양식이다.
`skills/orchestrator/SKILL.md`도 일반 Markdown 절차다. 별도 설치·등록을 요구하지 않는다.

다른 팀원 자료는 [references.md](references.md)에 원본과 적용 조건만 추가한다.
원본은 그대로 두고 필요한 부분만 연결한다. 활성 자료는 아직 등록하지 않았다.
실제 프로젝트 명령은 기존 팀 문서를 우선 확인한다. [config/project.md](config/project.md)는
프로젝트 경로와 정본 위치를 기록한 참고표이며, 작업 목표나 진행 상태를 저장하지 않는다.

## 제거한 것과 유지한 것

설치기, Python 관리 도구, 실행용 설정 파일, 자동 생성 단계, 도구 테스트와 자동 레지스트리를 제외했다.
개인 프로필 선택 파일이나 루트 연결 블록도 필요하지 않다.
작업 결과는 대화에 남기는 것이 기본이며 모든 작업마다 새로운 로그 파일을 만들 필요는 없다.

품질 우선·역할 우선·작성자 범위·동일 후보 검증·미실행 사실 공개·Astra 독립 감사 규칙은 유지했다.
배포 승인 자체는 기존 팀의 사람/CI 절차를 따른다.
선택적 평가·전환 안내는 필요할 때만 읽으며 실제 개발 작업의 선행 과제가 아니다.

## 기존 도구 포함 V3를 설치했었다면

이번 묶음은 과거 설치본을 자동으로 제거하지 않는다.
이전 자동 진입 규칙이 활성화돼 있으면 중복 적용 여부만 확인하고, 팀 공용 규칙을 함께 삭제하지 않는다.
자세한 내용은 [전환 안내](MIGRATION_V2_TO_V3.md)를 참고한다.

## 확인 범위

이 패키지는 문서 하네스다. 모델 호출·프로젝트 코드 실행·실제 배포 검증 결과를 포함하지 않는다.
실행한 검증과 수행하지 않은 검증을 구분하는 것이 운영 규칙이다.
