# Update Log

This file tracks repository-visible changes by commit so deployment syncs to IPC
and model hosts have a compact reference.

## 2026-03-12

### `feat: persist tool registry and promotion history`

- added a persistent `ToolRegistry` in `data/tool_registry.json`
- accepted `ToolSpec` contracts now survive process restarts
- tool execution outcomes now feed `ToolPromotionPolicy`
- promotion decisions are written back to the registry for later reuse
- added tests for registry persistence and agent-side contract recording

### `110c3ba` `feat: compact loop context and repair tool specs`

- added loop-context compression for small-model long runs
- injected `[Execution Brief]` and `[Compressed Loop History]` into the agent loop
- teacher responses can now return fenced `tool_spec` JSON and re-enter the build flow
- stabilized tests around tool repair and context compression

### `ab31854` `feat: close tool-spec loop and stabilize pytest`

- fixed Windows `pytest` temp-directory instability
- added `ToolLifecycleParser`
- wired incomplete `ToolSpec` generation into large-model escalation
- covered the first contract-repair loop with tests

### `955c4a4` `feat: scaffold tool lifecycle architecture`

- introduced `ToolSpec`, `TeacherRequest`, `ToolExecutionRecord`, and promotion contracts
- added discovery, builder, escalation, and promotion modules
- documented the OpenClaw-style lifecycle in `docs/TOOL_LIFECYCLE_ARCHITECTURE.md`

### `0468d3a` `fix: clean encoding artifacts and repo defaults`

- cleaned repository defaults and test configuration
- reduced encoding-related noise in tracked source files
- improved ignore rules for local runtime artifacts

### `0c0a81a` `docs: clarify network boundary and deployment roles`

- separated network/inference responsibilities from CoALA runtime responsibilities
- documented IPC, model host, Windows dev machine, and Alibaba Cloud roles
- made deployment boundaries explicit for future development
