# Sol Acceptance Record

필요한 위임·검토에서만 사용한다. 대화에 작성해도 되며 별도 파일 저장은 필수가 아니다.


TASK:
OWNER:
RISK: <LOW | MEDIUM | HIGH>
CANDIDATE:
DECISION: <ACCEPTED | CHANGES_REQUESTED | BLOCKED>

REQUIREMENT SATISFACTION:
CHANGED FILES:
MODEL / SESSION LEDGER: <actual models and evidence, including substitutions>

## Gates

| Gate | Required? | Status | Evidence at candidate |
|---|---|---|---|
| Implementation / investigation | yes | <state> | <result> |
| Verification | <risk-based> | <PASS/FAIL/NOT_RUN/BLOCKED/not-applicable> | <commands/results> |
| Independent review | <risk-based> | <state> | <review ID> |
| Astra audit | <HIGH or escalation> | <state> | <audit ID or approved substitute record> |
| Team-required CI | <team policy> | <state> | <actual evidence> |

FINDING DISPOSITION: <each ID: fixed/retested; minor tracked; disputed with evidence>
RESIDUAL RISK:
UNEXECUTED VALIDATION:
NEXT ACTION / HUMAN APPROVAL:

No ACCEPTED with unresolved BLOCKER/MAJOR or missing required verification/review.
Technical acceptance does not authorize push, merge, deployment, or production changes.
