# Task Packet

TASK: <unique-id / concrete task>
ROLE: <SCOUT | BUILDER | VERIFIER | REVIEWER | SPECIALIST | AUDITOR>
OBJECTIVE: <observable outcome>
SCOPE: <repo-relative paths and symbols>
WRITE SCOPE: <none, or explicit allowlist; never implicit whole repository>
CONTEXT: <requirement, relevant contracts, facts; not full chat history>
CONSTRAINTS: <team rules; no nested delegation; permissions; no unrelated changes>
DONE WHEN: <testable completion criteria>
RETURN: <required result fields and evidence>

RISK: <LOW | MEDIUM | HIGH; reason>
PROFILE: <selected profile>
MODEL_SLOT: <sol | terra | luna | astra>
MODEL_REQUESTED: <exact runtime ID>
MODEL_ACTUAL: unknown
BASE_REVISION: <base commit>
CANDIDATE: <commit or diff snapshot; required before validation/review>
WORKTREE: <absolute local workspace path>
ARTIFACT SCOPE: <allowed test cache/log paths, or none>
VALIDATION PLAN: <actual reviewed commands, cwd, side effects, approval requirements>
REFERENCE SNAPSHOTS: <selected reference IDs/paths/hashes, or none>
DEPENDENCIES: <needed predecessor task and exact result>
BUDGET / STOP: <agreed limits; stop repeated same-cause failure; do not weaken gates>
HUMAN APPROVAL: <required approvals and evidence, or not applicable>
