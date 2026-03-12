# Project Structure

This document defines the communication boundary inside the repository.

The rule is simple:

- the network / inference chain may change without requiring CoALA logic changes
- CoALA logic may change without touching FRP, forwarding, or model-host setup

## Layer 1: Network and inference chain

These files own connectivity and model exposure. They should absorb network
complexity so the rest of the project only sees one stable local endpoint.

- `scripts/local_async_gateway.py`
  - async wrapper for long FRP paths
- `scripts/cloud_397b_service.py`
  - standalone gateway for remote large model access
- `docker-compose.ipc.yml`
  - IPC runtime composition using host network
- `docker-compose.cloud.yml`
  - cloud gateway composition
- `deploy/ipc_external/`
  - external-machine Docker dev workflow
- `docs/IPC_FRP_QUICKSTART.md`
- `docs/LOCAL_ASYNC_GATEWAY.md`
- `docs/CLOUD_397B_SERVICE.md`

Boundary contract:

- expose a local OpenAI-compatible API
- preferred local address on IPC: `http://127.0.0.1:18081/v1`
- CoALA runtime should not need to know whether the upstream is Mac, 5070Ti,
  FRP, STCP, llama.cpp, or a remote gateway

## Layer 2: CoALA runtime and iteration surface

These files own agent behavior and are the primary place for day-to-day
development.

- `core/`
  - agent orchestration, routing, provider abstraction
- `memory/`
  - memory storage and retrieval
- `modules/`
  - tools, actions, perception, emotion helpers
- `skills/`
  - validation, storage, ranking, runtime loading, telemetry
- `config/`
  - typed settings and prompts
- `apps/web_console/`
  - isolated inspection and chat UI for IPC operations

Safe iteration rule:

- prefer changes here when tuning prompts, behavior, skills, memory, scoring,
  or UI
- avoid coupling these modules to FRP topology or host-specific addresses

## Layer 3: Data and verification

- `data/`
  - eval sets and runtime data
- `tests/`
  - behavior verification
- `docs/`
  - operations and architecture notes

## Deployment mapping

### 5070Ti or model host

- serves the model
- may run the async gateway
- should not be the default place for CoALA behavior development

### IPC

- receives the forwarded model endpoint
- runs CoALA and the web console
- is the default target for operational deployment

### Windows dev machine

- edits code and prepares sync bundles
- may run external Docker dev containers

### Alibaba Cloud relay

- stays a transport layer
- should not carry CoALA runtime state
