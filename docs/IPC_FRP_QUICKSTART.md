# IPC FRP Quickstart (5070Ti host model via local forward)

Use this when CoALA runs on IPC and the model runs on your 5070Ti host, reachable from IPC at:

- `http://127.0.0.1:18081/health`
- `http://127.0.0.1:18081/v1/models`

For unstable long FRP connections, run the async gateway on 5070Ti host and
forward it to IPC `127.0.0.1:18081`. See `docs/LOCAL_ASYNC_GATEWAY.md`.

## 1) Prepare env on IPC

```bash
cp .env.ipc.example .env
```

If you need remote large-model fallback, set `QWEN_API_KEY` in `.env`.

## 2) Host run (recommended first)

```bash
chmod +x scripts/run_agent_ipc.sh
./scripts/run_agent_ipc.sh
```

This script checks FRP model endpoint and starts `python main.py`.

## 3) Docker run on IPC

For FRP listener bound to `127.0.0.1:18081`, container must use host network:

```bash
docker compose -f docker-compose.ipc.yml build
docker compose -f docker-compose.ipc.yml run --rm coala
```

## 4) Quick troubleshooting

Check IPC local bind:

```bash
ss -lntp | grep ':18081'
curl -sS http://127.0.0.1:18081/health
curl -sS http://127.0.0.1:18081/v1/models
```

If health works but CoALA fails:

- verify `COALA_LOCAL_API_BASE=http://127.0.0.1:18081/v1`
- verify `COALA_LOCAL_ASYNC_ENABLED=true` when using async gateway
- verify `COALA_LOCAL_MODEL` is present in `/v1/models`
- force local route in prompt using `[small]` prefix
