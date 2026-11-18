# Independent Review / Astra Audit

필요한 위임·검토에서만 사용한다. 대화에 작성해도 되며 별도 파일 저장은 필수가 아니다.


TASK:
ROLE: <REVIEWER | AUDITOR>
STATUS: <PASS | CHANGES_REQUESTED | BLOCKED>
SUMMARY:
MODEL_REQUESTED:
MODEL_ACTUAL: <verified metadata or unknown>
MODEL_EVIDENCE:
SESSION_ID:
CANDIDATE:
REVIEW_SCOPE: <functional / architecture / security / other; exact coverage>
INDEPENDENCE: <fresh context? author of candidate? inherited author conclusions?>
CHANGES: none

## FINDINGS

| ID | Severity | Location | Trigger / impact | Evidence | Required change / test |
|---|---|---|---|---|---|

If no material issue was found, state that fact within the inspected scope. Do not invent findings.

EVIDENCE: <diff, surrounding code, call sites, requirements inspected>
VALIDATION: <executed checks or NOT_RUN; command/cwd/exit/log/candidate>
UNCOVERED_AREAS:
REFERENCES_USED:
RISKS:
CONFIDENCE: <HIGH | MEDIUM | LOW; reason>
ESCALATION:

PASS is a scoped review result, not a proof of zero defects and not Sol's final acceptance.
