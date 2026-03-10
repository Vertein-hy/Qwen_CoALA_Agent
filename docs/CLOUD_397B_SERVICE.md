# Cloud 397B Gateway Service

This mode skips local model routing and exposes a simple HTTP gateway.
Caller provides API key per request, so the service itself does not need to
store user secrets.
If `QWEN_API_KEY` (or `COALA_REMOTE_API_KEY_ENV`) is set in `.env`, the gateway
uses it as default and callers do not need to pass API key each time.

## 1) Start service

```bash
docker compose -f docker-compose.cloud.yml build
docker compose -f docker-compose.cloud.yml up -d
```

## 2) Health check

```bash
curl -sS http://127.0.0.1:18080/health
```

## 3) Request with API key in body

```bash
curl -sS http://127.0.0.1:18080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "sk-xxxx",
    "model": "qwen3.5-397b-a17b",
    "messages": [{"role":"user","content":"Hello, introduce yourself briefly."}],
    "temperature": 0.6,
    "max_tokens": 256
  }'
```

## 4) Request with API key in header

```bash
curl -sS http://127.0.0.1:18080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-xxxx" \
  -d '{
    "messages": [{"role":"user","content":"Give me practical suggestions for industrial AI deployment."}]
  }'
```

## 5) Request without API key (using default key from `.env`)

```bash
curl -sS http://127.0.0.1:18080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role":"user","content":"Give me practical suggestions for industrial AI deployment."}]
  }'
```

## 6) Stop service

```bash
docker compose -f docker-compose.cloud.yml down
```

## Notes

- Default upstream: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- Default model: `qwen3.5-397b-a17b`
- Default service port: `18080`
- If you expose this port to public network, add gateway auth / IP allowlist.
