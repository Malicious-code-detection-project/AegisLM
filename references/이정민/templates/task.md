# Task Packet

필요한 위임·검토에서만 사용한다. 대화에 작성해도 되며 별도 파일 저장은 필수가 아니다.


TASK: <unique-id / concrete task>
ROLE: <SCOUT | BUILDER | VERIFIER | REVIEWER | SPECIALIST | AUDITOR>
OBJECTIVE: <observable outcome>
SCOPE: <repo-relative paths and symbols>
WRITE SCOPE: <none, or explicit allowlist; never implicit whole repository>
CONTEXT: <requirement, relevant contracts, facts; not full chat history>
CONSTRAINTS: <team rules; no nested delegation; permissions; no unrelated changes>
DONE WHEN: <testable completion criteria>
RETURN: <required result fields and evidence>

## 필요한 보조 정보 — 관련 없는 항목은 생략

RISK: <LOW | MEDIUM | HIGH; reason>
PROFILE: 이정민
MODEL_SLOT: <sol | terra | luna | astra>
MODEL_REQUESTED: <exact runtime ID>
MODEL_ACTUAL: unknown
BASE_REVISION: <base commit>
CANDIDATE: <commit or diff snapshot; required before validation/review>
WORKTREE: <absolute local workspace path>
ARTIFACT SCOPE: <allowed test cache/log paths, or none>
VALIDATION PLAN: <actual reviewed commands, cwd, side effects, approval requirements>
REFERENCE SNAPSHOTS: <selected reference paths/versions; optional hashes, or none>
DEPENDENCIES: <needed predecessor task and exact result>
BUDGET / STOP: <agreed limits; stop repeated same-cause failure; do not weaken gates>
HUMAN APPROVAL: <required approvals and evidence, or not applicable>

