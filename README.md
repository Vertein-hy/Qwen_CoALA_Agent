# Qwen CoALA Agent

This repository is organized around one deployment principle:

- keep the network and inference chain isolated
- keep CoALA runtime iteration focused on the outer agent layer

In practice, CoALA should only depend on a stable local OpenAI-compatible
endpoint such as `http://127.0.0.1:18081/v1`. How that endpoint is provided
is a separate concern handled by FRP, STCP, async gateway, local forwards,
or cloud gateway services.

## Architecture split

### Network / inference chain

Responsible for connectivity, forwarding, long-response stability, and model
service exposure.

- `scripts/local_async_gateway.py`
- `scripts/cloud_397b_service.py`
- `docker-compose.ipc.yml`
- `docker-compose.cloud.yml`
- `deploy/ipc_external/`
- `docs/IPC_FRP_QUICKSTART.md`
- `docs/LOCAL_ASYNC_GATEWAY.md`
- `docs/CLOUD_397B_SERVICE.md`

### CoALA runtime layer

Responsible for agent behavior, memory, tools, skills, and inspection UI.

- `core/`
- `memory/`
- `modules/`
- `skills/`
- `config/`
- `apps/web_console/`

## Recommended operating model

### 5070Ti / model host

- run the actual local model server
- optionally run `local_async_gateway.py`
- do not run active CoALA development here unless debugging inference itself

### IPC

- terminate the FRP / local-forward chain into a stable local endpoint
- run CoALA containers and optional web console
- this is the main deployment target for field use

### Windows dev machine

- edit code
- package / sync code to IPC and model host
- optionally use `deploy/ipc_external/` for external Docker development

### Alibaba Cloud server

- stay focused on relay / access responsibilities
- avoid mixing agent runtime logic into this layer

## Start here

- IPC runtime quickstart: `docs/IPC_FRP_QUICKSTART.md`
- External Docker dev: `deploy/ipc_external/README.md`
- Communication boundary: `PROJECT_STRUCTURE.md`
- Web console: `docs/WEB_CONSOLE.md`
- Update log: `docs/UPDATE_LOG.md`
- Entrypoints: `docs/ENTRYPOINTS.md`
- Test matrix: `docs/TEST_MATRIX.md`
- Docs index: `docs/DOCS_INDEX.md`

## Entrypoints

- CLI: `python main.py`
- Web console: `python apps/web_console/server.py`
- Tests: `python scripts/run_tests.py --suite all`

## Packaging

Create a transfer bundle with:

```bash
bash scripts/package_for_external.sh
```
