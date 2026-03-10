# Project Structure

This document defines folder responsibilities and isolation boundaries.

## Core runtime

- `core/`: Agent orchestration, routing, model interface, and scoring.
- `memory/`: Long-term and short-term memory implementations.
- `modules/`: Tool execution and other runtime modules used by the agent loop.
- `config/`: Typed settings and prompt templates.

## Skill subsystem (plugin style)

- `skills/manager.py`: Entry point for skill validation and persistence.
- `skills/validator.py`: Static safety/readability validation for generated skills.
- `skills/catalog.py`: Metadata index for persisted skills (`index.json`).
- `skills/runtime_loader.py`: Controlled runtime plugin loader.
- `skills/internalized/`: Generated skill code and metadata index.

## Deployment and communication boundary

- `scripts/local_async_gateway.py`: Local async gateway used for host/device communication.
- `deploy/`: Docker and external deployment templates.
- `docker-compose*.yml`: Runtime composition for IPC/cloud/dev modes.

Important: keep communication-facing code isolated. For agent logic iterations,
prefer changes in `core/`, `skills/`, `memory/`, and `modules/` only.

## Data and tests

- `data/`: Evaluation sets and runtime data artifacts.
- `tests/`: Unit/integration tests for runtime behavior.
- `docs/`: Operations and architecture docs.
