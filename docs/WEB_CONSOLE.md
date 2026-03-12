# Web Console

The web console is part of the CoALA runtime layer, not the network layer.

Its purpose is:

- chat with `CognitiveAgent`
- inspect internalized skills
- inspect skill and memory event logs
- validate candidate skill code

It should stay isolated from FRP topology, gateway internals, and host-to-host
transport logic.

## Start service on IPC

```bash
cd /dockerdata/Qwen_CoALA_Agent
docker compose -f docker-compose.ipc.yml up -d coala-web
docker compose -f docker-compose.ipc.yml ps
curl -sS http://127.0.0.1:7860/api/health
```

Default bind:

- `COALA_WEB_HOST=127.0.0.1`
- `COALA_WEB_PORT=7860`

## Access from Windows via FRP STCP

Keep the service local to IPC and expose it through a separate STCP pair.

Example:

- IPC local service: `127.0.0.1:7860`
- Windows visitor bind: `127.0.0.1:17860`

Then open:

- `http://127.0.0.1:17860/`

## Useful APIs

- `GET /api/health`
- `POST /api/chat` with `{"message":"..."}`
- `GET /api/skills`
- `GET /api/logs?type=skill&limit=50`
- `GET /api/logs?type=memory&limit=50`
- `POST /api/validate-skill` with `{"code":"def ..."}`

## Isolation rule

If a change is about:

- ports
- STCP / FRP
- host forwarding
- async gateway topology

it does not belong in the web console.
