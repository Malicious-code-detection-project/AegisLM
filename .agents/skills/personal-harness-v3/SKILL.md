---
name: personal-harness-v3
description: Load an explicitly selected repository personal harness through references/<profile>/index.md. Use only when the user requests the personal V3 workflow; do not replace team rules, choose a user automatically, or load every reference folder.
---

# Personal Harness V3 Router

Read applicable team instructions first. Find the repository/worktree root.
Resolve a profile from the user's explicit selection or root `.active-profile`.
Only allow `^[a-z][a-z0-9_-]{0,31}$`. No selection means no personal harness.
Do not follow profile paths or symlinks outside the repository.
Read `references/<profile>/index.md` and follow its progressive loading rules.
If it contains `skills/orchestrator/SKILL.md`, use that workflow for non-trivial tasks.
Do not claim automatic model switching: use only actual runtime capabilities.
This dispatcher does not choose roles for other personal profiles or override team policy.
