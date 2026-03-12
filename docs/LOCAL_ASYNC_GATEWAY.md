# Local Async Gateway

Use this when IPC reaches the model host over FRP and long synchronous model
responses are unstable.

This gateway belongs to the network / inference chain layer. Its job is to hide
long upstream inference behind short submit-and-poll requests so CoALA can keep
using one stable local endpoint on IPC.

## Flow

1. IPC submits a job
2. IPC polls job status
3. Gateway returns final text

CoALA still only sees the IPC-local gateway endpoint.

## 1) Run upstream model on model host

Example upstream endpoint:

- `http://127.0.0.1:8000/v1`

## 2) Start async gateway on model host

```bash
cd Qwen_CoALA_Agent
export COALA_UPSTREAM_API_BASE=http://127.0.0.1:8000/v1
export COALA_UPSTREAM_MODEL=Qwen3.5-9B-Q4_K_M.gguf
export COALA_ASYNC_GATEWAY_PORT=8001
python scripts/local_async_gateway.py
```

## 3) Forward gateway to IPC

Forward model-host `127.0.0.1:8001` to IPC local `127.0.0.1:18081`.

Then IPC should see:

- `http://127.0.0.1:18081/health`
- `http://127.0.0.1:18081/v1/models`
- `http://127.0.0.1:18081/jobs`

## 4) IPC `.env` settings

```env
COALA_LOCAL_API_BASE=http://127.0.0.1:18081
COALA_LOCAL_ASYNC_ENABLED=true
COALA_LOCAL_ASYNC_SUBMIT_PATH=/jobs
COALA_LOCAL_ASYNC_STATUS_PATH_TEMPLATE=/jobs/{job_id}
COALA_LOCAL_ASYNC_POLL_INTERVAL_S=1.0
COALA_LOCAL_ASYNC_TIMEOUT_S=600
```

Note:

- this mode points `COALA_LOCAL_API_BASE` at the gateway root, not `/v1`
- the gateway itself exposes the async submit path and compatible status paths

## 5) Quick checks on IPC

```bash
curl -sS http://127.0.0.1:18081/health
curl -sS http://127.0.0.1:18081/v1/models
```

Then a minimal runtime check:

```bash
python3 - <<'PY'
from core.llm_interface import LLMInterface

llm = LLMInterface()
result = llm.chat_with_meta(
    [{"role": "user", "content": "[small] 只回复OK"}],
    temperature=0.1,
)
print(result.route, result.model_name, result.content[:80])
PY
```
