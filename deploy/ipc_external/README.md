# IPC / External Dev Deployment

This mode is for development outside the IPC while preserving the same
architecture boundary:

- the network and inference chain stays externalized
- the CoALA container only sees a stable local endpoint from `coala.env`

Use this mode when you want to iterate on CoALA behavior from another machine
without changing the field deployment topology.

## Assumption

Your development machine can already reach the forwarded model endpoint, and
that endpoint behaves like a local OpenAI-compatible service.

Default example:

- `http://127.0.0.1:18081/v1`

## 1) Prepare environment

```bash
cp deploy/ipc_external/coala.env.example deploy/ipc_external/coala.env
```

Edit `deploy/ipc_external/coala.env`:

- `COALA_LOCAL_API_BASE`
  - point this to the endpoint already exposed on the development machine
- `COALA_LOCAL_ASYNC_ENABLED=true`
  - recommended when the upstream path crosses FRP
- `QWEN_API_KEY`
  - only needed if you want remote large-model fallback

## 2) Start dev container

```bash
bash deploy/ipc_external/devctl.sh up
```

## 3) Develop and run

```bash
bash deploy/ipc_external/devctl.sh health
bash deploy/ipc_external/devctl.sh shell
bash deploy/ipc_external/devctl.sh run
bash deploy/ipc_external/devctl.sh test
```

## 4) Stop

```bash
bash deploy/ipc_external/devctl.sh down
```

## Boundary reminder

If you are changing prompts, routing, memory, skills, or the web console, work
in the regular CoALA modules.

If you are changing ports, FRP exposure, async job submission, or host-to-host
forwarding, work in the network / inference chain files instead.
