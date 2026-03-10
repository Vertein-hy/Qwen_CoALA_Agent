# Local Async Gateway (for FRP stability)

When IPC -> model host traffic is over FRP and long responses get reset,
run this async gateway on the model host (e.g. 5070Ti machine).

IPC then only does short polling requests:

1) submit job
2) poll status
3) fetch final text

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

## 3) FRP forwarding

Forward model-host `127.0.0.1:8001` to IPC local `127.0.0.1:18081`.

Then IPC should see:

- `http://127.0.0.1:18081/health`
- `http://127.0.0.1:18081/v1/models`
- `http://127.0.0.1:18081/v1/jobs`

## 4) IPC .env settings

```env
COALA_LOCAL_API_BASE=http://127.0.0.1:18081/v1
COALA_LOCAL_ASYNC_ENABLED=true
COALA_LOCAL_ASYNC_SUBMIT_PATH=/jobs
COALA_LOCAL_ASYNC_STATUS_PATH_TEMPLATE=/jobs/{job_id}
COALA_LOCAL_ASYNC_POLL_INTERVAL_S=1.0
COALA_LOCAL_ASYNC_TIMEOUT_S=600
```

## 5) Quick check on IPC

```bash
curl -sS http://127.0.0.1:18081/health
curl -sS http://127.0.0.1:18081/v1/models
```

Then run:

```bash
python3 - <<'PY'
from core.llm_interface import LLMInterface
llm = LLMInterface()
r = llm.chat_with_meta([{"role":"user","content":"[small] 只回复OK"}], temperature=0.1)
print(r.route, r.model_name, r.content[:80])
PY
```
