# IPC/External Dev Deployment

This folder is for running CoALA on an IPC or external development machine with Docker,
while the LLM inference stays on your high-compute PC.

## 1) Prepare environment

```bash
cp deploy/ipc_external/coala.env.example deploy/ipc_external/coala.env
```

Edit `deploy/ipc_external/coala.env`:

- `COALA_LOCAL_API_BASE` should point to your forwarded local endpoint.
  - Current default: `http://127.0.0.1:18081/v1`
- `COALA_LOCAL_ASYNC_ENABLED=true` is recommended when endpoint is over FRP.
- Ensure model host runs `scripts/local_async_gateway.py` and FRP forwards gateway port.
- If you need remote large model, set `QWEN_API_KEY`.

## 2) Start dev container

```bash
bash deploy/ipc_external/devctl.sh up
```

## 3) Develop / run

```bash
# Open shell
bash deploy/ipc_external/devctl.sh shell

# Run CLI agent
bash deploy/ipc_external/devctl.sh run

# Run tests
bash deploy/ipc_external/devctl.sh test
```

## 4) Stop

```bash
bash deploy/ipc_external/devctl.sh down
```

## Quick connectivity check

```bash
bash deploy/ipc_external/devctl.sh health
```
