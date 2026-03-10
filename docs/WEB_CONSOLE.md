# Web Console (IPC + FRP STCP)

This console provides:

- chat with `CognitiveAgent`
- skill index and `custom_skills.py` inspection
- skill/memory event log inspection
- skill code validation API

It is designed to be isolated from model gateway/networking code.

## 1) Start service on IPC

```bash
cd /dockerdata/Qwen_CoALA_Agent
docker compose -f docker-compose.ipc.yml up -d coala-web
docker compose -f docker-compose.ipc.yml ps
curl -sS http://127.0.0.1:7860/api/health
```

Default bind:

- `COALA_WEB_HOST=127.0.0.1`
- `COALA_WEB_PORT=7860`

## 2) Access from Windows via FRP STCP

You already use STCP and connect from MobaXterm to `127.0.0.1 (pc)`.
Add one more STCP forwarding pair for the web console:

- IPC local service: `127.0.0.1:7860`
- PC visitor local bind: `127.0.0.1:<your_port>` (for example `17860`)

Then open on PC browser:

- `http://127.0.0.1:17860/`

## 3) Useful APIs

- `GET /api/health`
- `POST /api/chat` body: `{"message":"..."}`
- `GET /api/skills`
- `GET /api/logs?type=skill&limit=50`
- `GET /api/logs?type=memory&limit=50`
- `POST /api/validate-skill` body: `{"code":"def ..."}`
