# Small-Model Agent Reference Principles

This document converts your `s01-s12` notes into actionable CoALA guidance.
It is reference-only. We do not copy external framework code or protocols.

## Scope

- Reuse ideas only, not implementation.
- Keep all changes inside current CoALA modules.
- Every new capability must be testable, observable, and reversible.

## Mapping (s01-s12)

1. `s01` One loop + one tool first:
- Keep `core/agent.py` loop minimal and stable.
- Validate each new capability with one tool before scaling.

2. `s02` Add tools without changing the loop:
- Register new tools in `modules/tools.py` dispatch map.
- Avoid tool-specific branches in the core loop.

3. `s03` Plan before acting:
- Add a lightweight planning phase (3-5 steps max).
- Persist plan summary in logs, not in long-term memory by default.

4. `s04` Split big tasks, isolate context:
- Use isolated `messages[]` buffers for sub-tasks.
- Return only sub-task conclusions to the main thread.

5. `s05` Load knowledge on demand:
- Inject knowledge via tool observations.
- Keep system prompt short: role + rules + language policy.

6. `s06` Context compression:
- Layer 1: recent-window truncation.
- Layer 2: summarize intermediate reasoning.
- Layer 3: index events into memory and retrieve on demand.

7. `s07` Persisted task graph:
- Store task graph under `data/tasks/*.json`.
- Minimal fields: `task_id/status/priority/deps/owner/updated_at`.

8. `s08` Background slow operations:
- Execute slow tools in background worker.
- Notify main loop asynchronously on completion.

9. `s09` Delegate to teammates:
- Define task interfaces first, then add teammate agents.
- Keep orchestration layer separate from core loop logic.

10. `s10` Unified request-response contract:
- Standard message schema for agent-to-agent communication.
- Required keys: `request_id/intent/payload/deadline/status`.

11. `s11` Self-assign from board:
- Agents claim tasks from persisted board by capability tags.
- Start with single-node implementation first.

12. `s12` Task/worktree isolation:
- Task state and working directory are separate concerns.
- Bind `task_id -> work_dir` when multi-worktree is needed.

## Priority for CoALA (small-model first)

1. Implement `s03 + s06` (planning + compression) first.
2. Then add `s07` (persisted task graph).
3. Finally implement `s08-s12` (background + multi-agent collaboration).
