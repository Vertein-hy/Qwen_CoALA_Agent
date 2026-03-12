# IPC FRP Quickstart

Use this when:

- the model runs on another machine such as your 5070Ti host or Mac
- IPC receives that model through FRP / STCP / local forward
- CoALA itself runs on the IPC

The goal is to collapse all network complexity into one IPC-local endpoint.

## Target contract on IPC

Before starting CoALA, IPC should have a stable local endpoint such as:

- `http://127.0.0.1:18081/health`
- `http://127.0.0.1:18081/v1/models`
- `http://127.0.0.1:18081/v1/chat/completions` or `/v1/completions`

Recommended endpoint:

- `http://127.0.0.1:18081/v1`

## Recommended topology

- model host runs the actual model server
- if long FRP responses are unstable, model host also runs
  `scripts/local_async_gateway.py`
- IPC only consumes the forwarded local endpoint
- CoALA never talks directly to FRP topology

## 1) Verify endpoint on IPC

```bash
curl -sS http://127.0.0.1:18081/health
curl -sS http://127.0.0.1:18081/v1/models
ss -lntp | grep ':18081'
```

If long responses are unstable, see `docs/LOCAL_ASYNC_GATEWAY.md`.

## 2) Prepare `.env` on IPC

Use these as the important minimum:

```env
COALA_LOCAL_PROVIDER=openai_compat
COALA_LOCAL_MODEL=Qwen3.5-9B-Q4_K_M.gguf
COALA_LOCAL_API_BASE=http://127.0.0.1:18081/v1
COALA_LOCAL_REQUIRE_API_KEY=false
COALA_LOCAL_API_KEY=local-key
COALA_LOCAL_SUPPORTS_TOP_K=false
```

If IPC is consuming the async gateway:

```env
COALA_LOCAL_ASYNC_ENABLED=true
COALA_LOCAL_ASYNC_SUBMIT_PATH=/jobs
COALA_LOCAL_ASYNC_STATUS_PATH_TEMPLATE=/jobs/{job_id}
COALA_LOCAL_ASYNC_POLL_INTERVAL_S=1.0
COALA_LOCAL_ASYNC_TIMEOUT_S=600
```

## 3) Start CoALA directly on IPC

```bash
chmod +x scripts/run_agent_ipc.sh
./scripts/run_agent_ipc.sh
```

This script checks the local model endpoint first, then starts `python main.py`.

## 4) Start CoALA in Docker on IPC

When the forwarded endpoint is bound to `127.0.0.1:18081`, use host network:

```bash
docker compose -f docker-compose.ipc.yml build
docker compose -f docker-compose.ipc.yml run --rm coala
```

## 5) Optional web console on IPC

```bash
docker compose -f docker-compose.ipc.yml up -d coala-web
curl -sS http://127.0.0.1:7860/api/health
```

## Troubleshooting

- `health` works but CoALA fails:
  - verify `COALA_LOCAL_API_BASE=http://127.0.0.1:18081/v1`
  - verify `COALA_LOCAL_MODEL` appears in `/v1/models`
  - verify `COALA_LOCAL_ASYNC_ENABLED=true` when using async gateway
- `chat/completions` is weak but `completions` works:
  - current provider layer already falls back to `/completions`
- FRP long responses reset:
  - move IPC to the async gateway path and keep CoALA talking to the IPC-local
    gateway endpoint only
