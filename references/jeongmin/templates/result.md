# Result Packet

TASK:
ROLE:
STATUS: <DONE | BLOCKED | FAILED; VERIFIER uses PASS | FAIL | BLOCKED>
SUMMARY:

MODEL_REQUESTED:
MODEL_ACTUAL: <runtime evidence or unknown>
MODEL_EVIDENCE: <status/metadata location; not self-identification>
SESSION_ID:
WORKTREE:
CANDIDATE:

CHANGES: <source files and summary; none for read-only roles>
ARTIFACTS: <logs/cache/reports, separate from source edits>
EVIDENCE: <file/symbol/line at candidate, observations, outputs>

## VALIDATION

| Command / cwd | Status | Exit code | Key result | Log | Candidate |
|---|---|---|---|---|---|
| <actual command or planned command> | <PASS/FAIL/NOT_RUN/BLOCKED> | <integer or not-run> | <observed only> | <path> | <snapshot> |

REFERENCES_USED: <IDs, source paths, versions/hashes>
RISKS: <known gaps and unverified assumptions>
CONFIDENCE: <HIGH | MEDIUM | LOW; brief evidence-based reason>
ESCALATION: <decision needed from Sol, or none>
PROCESS_VIOLATIONS: <out-of-scope change or permission issue, or none>

A subtask DONE is not final acceptance. Never invent command execution or model identity.
