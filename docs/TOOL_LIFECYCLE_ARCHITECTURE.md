# Tool Lifecycle Architecture

This document describes the next-layer architecture for OpenClaw-style tool
usage with a small-model-first workflow.

## Goal

The agent should be able to:

1. enter a new project
2. inspect available tools
3. decide whether a tool fits the task
4. build a new tool contract if no tool fits
5. ask a larger model for structured help when blocked
6. complete the work
7. decide whether the resulting tool is worth reusing or internalizing

## Lifecycle

### 1. Project intake

Input:

- user task
- project constraints
- available files / environment facts

Output:

- `ProjectToolContext`

### 2. Tool discovery

Input:

- `ProjectToolContext`
- known `ToolSpec` records

Output:

- ranked `ToolMatchResult` records

Scoring dimensions:

- goal match
- input/output compatibility
- environment compatibility
- historical reuse fit
- cost / risk

### 3. Contract-first tool building

If no candidate is good enough, the agent must create a `ToolSpec` before
writing code.

Minimum contract:

- purpose
- inputs
- outputs
- side effects
- failure modes
- examples

### 4. Teacher escalation

The small model should not ask the large model with raw chain-of-thought.
Instead it emits a structured `TeacherRequest` containing:

- goal
- current contract
- failed attempts
- constraints
- requested help type

### 5. Execution logging

Every tool run should produce a `ToolExecutionRecord` so the system can learn:

- did it work
- what did it cost
- was it reusable
- did it match the intended interface

### 6. Promotion policy

Tool outputs should move through three levels:

- episode-only
- project-level reusable
- globally internalized skill

Promotion should depend on explicit score, not a free-form model opinion.

## File map

- `skills/tool_contracts.py`
  - dataclasses for tool specs, teacher requests, execution records
- `skills/tool_discovery.py`
  - discovery and scoring
- `skills/tool_builder.py`
  - contract validation and build planning
- `skills/tool_escalation.py`
  - larger-model request assembly
- `skills/tool_promotion.py`
  - reuse and internalization scoring

## Integration boundary

These modules are scaffolding for future integration.
They should not change the existing CoALA runtime flow until the wiring plan is
explicitly chosen.
