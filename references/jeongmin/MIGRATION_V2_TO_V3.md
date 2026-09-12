# V2 → V3 · 개인 하네스로 분리

## 확인한 이전 자료

Library에 저장된 V2/V2.1 계열 `AGENTS.md`, `harness.md`, `routing.md`, `handoff.md`,
`review.md`, `SKILL.md`를 읽고 핵심 규칙을 이어받았다. 이전 root README를 프로젝트 소개로
유지한다는 규칙도 보존했다. 원본 저장소의 특정 commit을 확인한 것은 아니므로 commit 단위
자동 업그레이드나 기존 파일의 byte-for-byte 변환이라고 주장하지 않는다.

| 기존 위치/역할 | V3 개인 위치/처리 |
|---|---|
| 루트 `README.md` | 프로젝트 소개 그대로 보존 |
| 루트 `AGENTS.md` | 팀 규칙 유지, 필요할 때 opt-in 프로필 진입 블록만 검토 후 추가 |
| `docs/agents/harness.md` | 개인 설명은 `references/jeongmin/harness/harness.md` |
| `docs/agents/{routing,handoff,review}.md` | 개인 규칙은 같은 이름으로 `references/jeongmin/harness/` |
| `.agents/skills/orchestrator/SKILL.md` | 기존 skill 보존, 별도 `personal-harness-v3` dispatcher 선택 설치 |
| Sol / Terra / Luna | 그대로 유지하되 역할과 실제 model ID 분리 |
| 9항목 task packet | 그대로 유지, 모델·후보·권한·근거·위험 정보 추가 |
| 고위험 검증 | Astra 독립 감사 gate 추가 |

## 꼭 유지할 것

품질을 낮춰 비용을 줄이지 않는다. 과도한 위임을 피하고 역할을 먼저 정한다.
동시 writer scope를 겹치지 않는다. Builder 완료와 최종 수용은 별개다.
Reviewer와 Verifier는 소스를 고치지 않는다. 미실행 검증·불확실성을 숨기지 않는다.
README를 harness로 바꾸지 않는다. 장황한 내부 추론 대신 결론·증거·위험을 인계한다.

## 바뀐 부분

- Astra를 상위 지휘자로 자동 승격하지 않는다. Sol은 조율/기술적 수용을 유지한다.
- HIGH gate에서는 독립 Astra audit를 요구한다. 전체 리뷰를 겸한 경우 불필요한 중복 리뷰를 피한다.
- 개인 프로필은 팀 보안/품질 정책을 우회하지 않는다. 전역·하위 AGENTS 실제 로딩 순서는 런타임을 따른다.
- 모델명·권한은 설명과 실행 설정이 다르다. 실제 child metadata와 effective sandbox를 확인한다.
- `.active-profile`과 로컬 JSON은 자체 관례다. Codex 연결은 별도 생성/검토 단계다.
- 테스트는 소스를 바꾸지 않더라도 부작용이 있을 수 있어 artifact scope와 격리를 명시한다.

## 실제 이전 절차

작업 중인 변경과 기존 하네스 파일을 먼저 확인한다. 기본 설치의 dry-run을 실행하고 충돌을 검토한다.
`references/jeongmin/`에 기존 파일이 있으면 설치기가 덮어쓰지 않는다. 별도의 `--profile jeongmin-v3`
설치로 내용을 비교하거나, 기존 개인 파일을 직접 보관하고 필요한 변경만 적용한다.

팀 root AGENTS가 V2의 모델/skill 사용을 **의무화**했다면 개인 V3와 동시에 서로 모순되는 지시를
활성화하지 않는다. 팀 리뷰로 개인 opt-in 분기를 허용하거나 기존 정책을 명시적으로 개정한다.
충돌이 해결되기 전에는 개인 프로필의 충돌 지시 적용을 중단한다.

실제 프로젝트 명령/경로는 로컬 설정으로 옮긴다. 공용 명령이 팀 문서에 있으면 그 정본을 링크한다.
기존 `.agents/skills/orchestrator`를 지우지 말고 필요하면 새 dispatcher를 명시적으로 선택한다.
대표 LOW/MEDIUM/HIGH 작업에서 실제 모델·권한·gate 동작을 확인하고 전환한다.
