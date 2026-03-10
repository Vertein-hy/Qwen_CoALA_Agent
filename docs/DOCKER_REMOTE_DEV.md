# Docker Remote Dev (via IPC STCP)

This setup lets you run CoALA anywhere while keeping code mounted locally.
Only requirement: your machine can tunnel to the IPC and reach the model API.

## 1) Build image

```bash
docker compose -f docker-compose.dev.yml build
```

## 2) Create host tunnel to IPC model endpoint

Replace placeholders:

```bash
ssh -NT -L 16006:127.0.0.1:18081 <ipc_user>@127.0.0.1 -p <ipc_stcp_port>
```

Quick host check:

```bash
curl -sS http://127.0.0.1:16006/health
curl -sS http://127.0.0.1:16006/v1/models
```

## 3) Run CoALA in container (with source mounted)

```bash
docker compose -f docker-compose.dev.yml run --rm coala
```

`COALA_LOCAL_API_BASE` in container is controlled by `COALA_LOCAL_API_BASE_DOCKER`
and defaults to:

`http://host.docker.internal:16006/v1`

If needed, override once:

```bash
COALA_LOCAL_API_BASE_DOCKER=http://host.docker.internal:16006/v1 docker compose -f docker-compose.dev.yml run --rm coala
```

## 4) Optional smoke test inside container

```bash
docker compose -f docker-compose.dev.yml run --rm coala python - <<'PY'
import os
import requests

base = os.environ.get("COALA_LOCAL_API_BASE", "").rstrip("/")
print("base =", base)
print("models =", requests.get(base + "/models", headers={"Authorization": "Bearer local-key"}, timeout=30).status_code)
PY
```

## Notes

- Code is bind-mounted (`./:/app`), so local edits are visible immediately.
- Dependency changes still require rebuild.
- If `host.docker.internal` is unavailable on your Docker engine, use host IP and set `COALA_LOCAL_API_BASE` explicitly.
