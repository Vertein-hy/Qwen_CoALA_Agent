# Qwen CoALA Agent

Deployment files for IPC / external-machine Docker development:

- `deploy/ipc_external/README.md`
- `deploy/ipc_external/docker-compose.yml`
- `deploy/ipc_external/coala.env.example`
- `deploy/ipc_external/devctl.sh`
- `docs/LOCAL_ASYNC_GATEWAY.md` (recommended for FRP long-response stability)
- `PROJECT_STRUCTURE.md` (folder responsibilities + communication isolation boundary)

Pack a transfer bundle:

```bash
bash scripts/package_for_external.sh
```
