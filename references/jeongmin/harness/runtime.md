# Runtime · 역할과 실제 실행을 분리

## 1. 자동으로 되는 것과 안 되는 것

`references/jeongmin/`은 임의의 개인 문서 경로다. 파일을 복사한다고 모든 도구가 이를 자동 로딩하지 않는다.
`.active-profile`도 **이 하네스가 정한 관례**다. 루트 `AGENTS.md`의 opt-in 라우터 또는 명시적 시작 프롬프트가 읽어야 한다.
`models.local.json` 역시 Codex의 네이티브 설정이 아니다. 도구가 읽을 설정/프롬프트로 연결해야 한다.

Codex 공식 문서의 AGENTS/skill/custom-agent 경로를 적용한 선택적 연결을 제공한다. [SOURCES](../SOURCES.md)의 S1–S4 참고.
다른 도구에서는 그 도구가 실제로 지원하는 규칙·skill·모델 선택 기능을 사용한다.
지원하지 않는 spawn 호출이나 자동 모델 전환이 일어났다고 주장하지 않는다.

## 2. 지시·권한의 실제 순서

플랫폼의 system/developer/user 지시와 관리자 정책, 파일의 신뢰 수준을 먼저 지킨다.
Codex는 일반적으로 전역 지시와 프로젝트 루트부터 시작 작업 디렉터리까지의 지시를 조합하고,
각 디렉터리에서 `AGENTS.override.md`를 `AGENTS.md`보다 먼저 고려한다. 하위 지시가 상위 지시를 구체화/대체할 수 있다. [S1]
따라서 '루트 AGENTS가 어떤 경우든 기술적으로 최우선'이라고 가정하지 않는다.
개인 하네스는 팀 규칙을 우회하는 용도로 사용하지 않는다. 충돌은 보고하고 개인 지시 적용을 중단한다.

루트에서 시작했다고 모든 하위 `AGENTS.md`가 이미 로딩됐다고 가정하지 않는다.
실제 수정 경로로 내려가기 전에 그 경로에 적용되는 규칙을 확인한다.
자료 폴더의 다른 사용자 AGENTS는 내 소스 작업의 지시를 바꾸는 근거가 아니다.

## 3. 로컬 파일

```text
<repo>/.active-profile                       # jeongmin 한 줄
<repo>/.harness-local/jeongmin/models.local.json
<repo>/.harness-local/jeongmin/project.local.json
<repo>/.harness-local/jeongmin/runs/<task-id>/ # 필요한 경우 직접 생성
```

이 파일은 Git에서 제외한다. API 키·토큰·계정 비밀번호는 모델 설정이나 reference에 저장하지 않는다.
모델과 reasoning 설정의 기본 후보는 [models.example.json](../config/models.example.json)에 있다.
공식 문서에 이름이 있어도 내 계정/CLI에서 사용 가능하다는 뜻은 아니다.

## 4. 시작 확인

- 저장소/worktree 경로, 사용자 선택 프로필, 적용 팀 규칙.
- CLI 이름과 버전, 부모 모델, 하위 모델을 선택할 수 있는지.
- 실제 sandbox/승인 정책, 허용된 파일·네트워크·검증 명령.
- native / manual-multi-session / single-session 실행 모드.

모델 슬롯마다 요청 model ID와 실제 실행 ID를 구분한다. 런타임 메타데이터나 상태 출력으로 확인하고,
확인 불가하면 actual은 unknown이다. 직접 확인한 뒤에만 availability를 available로 바꾼다.
`check`는 설정값을 검사할 뿐 계정 접근성을 실시간 검사하지 않는다.

## 5. Codex 연결

루트에서 다음을 실행하면 설정 초안을 **로컬 staging 폴더에만** 생성한다.

```bash
python3 references/jeongmin/tools/harness.py render-codex --repo . --profile jeongmin
```

현재 공식 형식의 custom-agent TOML에는 `name`, `description`, `developer_instructions`,
`model`, `model_reasoning_effort`, `sandbox_mode`를 넣는다. [S2]
생성 경로는 `.harness-local/jeongmin/codex-generated/`다.
파일을 검토한 후 아래처럼 신규 파일만 복사한다. 같은 이름이 이미 있으면 자동 덮어쓰지 않는다.

```bash
mkdir -p .codex/agents
cp -n .harness-local/jeongmin/codex-generated/v3-*.toml .codex/agents/
```

부모 세션은 Sol로 시작한다. 모델 ID는 로컬 설정/CLI에서 확인한 값을 쓴다.
예시 기본 후보로 시작하는 명령은 다음과 같다. [S2, S4]

```bash
codex --model gpt-5.6-sol --sandbox workspace-write --ask-for-approval on-request
```

첫 입력으로 `bootstrap` 출력과 실제 작업을 전달한다.
생성된 하위 에이전트 이름은 `v3-jeongmin-luna-scout`, `v3-jeongmin-luna-verifier`,
`v3-jeongmin-terra-builder`, `v3-jeongmin-terra-reviewer`,
`v3-jeongmin-astra-specialist`, `v3-jeongmin-astra-auditor`다.
`Sol`은 부모이므로 별도 Director 하위 에이전트를 만들지 않는다.
다른 프로필 이름으로 설치하면 그 이름이 들어간다.

현재 세션의 live 권한 override가 child 설정에 영향을 줄 수 있다. TOML의 read-only만 믿지 말고
실제 child 권한을 확인한다. 출처 S2/S5에 있는 권한 설명을 따르며 무제한 권한 플래그를 사용하지 않는다.
설정 파일을 만들어도 설치된 CLI가 이 형식을 지원하지 않으면 동작하지 않는다.
그 경우 설정을 강제로 맞추거나 가짜 실행을 보고하지 말고 아래 수동 모드로 진행한다.

## 6. 수동 모드와 대체

각 모델의 별도 세션에 동일 후보를 제공하고 task/result 양식으로 인계한다.
파일/도구 접근은 승인된 환경만 사용한다. 폐쇄망 자료를 모델 사용을 위해 외부로 무단 전송하지 않는다.
모델 변경을 지원하지 않는 단일 세션에서는 역할별 자기 점검을 할 수 있지만
이를 '4모델 실행'이나 '독립 리뷰'라고 부르지 않는다. 필수 독립 gate가 있으면 BLOCKED다.

모델 부재 시 자동 저성능 대체는 없다. Sol이 후보의 적합성과 실제 모델을 기록한다.
Astra 필수 gate의 대체 승인 절차는 [escalation](escalation.md)을 따른다.

## 7. 최초 smoke test

작은 read-only Scout 조사 → 한정된 Builder 수정 → Verifier → fresh Reviewer 순서로 시험한다.
Astra는 읽기 전용 설계 검토 한 건으로 model ID와 경계 준수를 확인한다.
관찰한 모델·권한·명령·결과를 기록한다. 자동 생성 파일만으로 이 시험이 완료됐다고 간주하지 않는다.
