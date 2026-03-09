# Local Model Setup (macOS + Windows)

This project supports two local-inference routes:

1. `safetensors` route (no conversion): run an OpenAI-compatible server (vLLM/SGLang/TGI).
2. `GGUF` route: convert from HF weights, then run `llama.cpp` server.

For macOS (especially Apple Silicon), the GGUF + llama.cpp route is usually the most practical.
For Windows migration, GGUF is also a stable and portable option.

## Model Name Used by This Project

Current default local model id in config:

- `Qwen/Qwen3.5-9B-Instruct`

If you use `Qwen/Qwen3.5-9B` instead, keep it consistent in both:

- server startup model
- `COALA_LOCAL_MODEL` in `.env`

## Route A: Keep `safetensors` (No GGUF Conversion)

Set:

```bash
COALA_LOCAL_PROVIDER=openai_compat
COALA_LOCAL_API_BASE=http://127.0.0.1:8000/v1
COALA_LOCAL_MODEL=Qwen/Qwen3.5-9B-Instruct
COALA_LOCAL_REQUIRE_API_KEY=false
```

Then run any local OpenAI-compatible serving stack that can load HF safetensors.

## Route B: Convert to GGUF (Recommended for macOS + Windows portability)

Prerequisites:

- `git`
- `python` (for converter)
- `huggingface-cli`
- `llama.cpp` repo

### 1) Convert

Use script:

- `scripts/convert_qwen_to_gguf.sh`

Example:

```bash
bash scripts/convert_qwen_to_gguf.sh Qwen/Qwen3.5-9B-Instruct Q4_K_M
```

Output:

- `models/gguf/Qwen3.5-9B-Instruct-Q4_K_M.gguf`

### 2) Start local OpenAI-compatible endpoint

macOS:

```bash
bash scripts/run_llama_server_mac.sh models/gguf/Qwen3.5-9B-Instruct-Q4_K_M.gguf
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_llama_server_windows.ps1 -ModelPath "models/gguf/Qwen3.5-9B-Instruct-Q4_K_M.gguf"
```

Both scripts expose:

- `http://127.0.0.1:8000/v1`

## Project Env for llama.cpp Server

```bash
COALA_LOCAL_PROVIDER=openai_compat
COALA_LOCAL_API_BASE=http://127.0.0.1:8000/v1
COALA_LOCAL_MODEL=qwen-local-gguf
COALA_LOCAL_REQUIRE_API_KEY=false
COALA_LOCAL_API_KEY=local-key
```

Notes:

- `COALA_LOCAL_MODEL` should match the model alias passed to llama server (`--alias`).
- With GGUF backend, keep `COALA_LOCAL_SUPPORTS_TOP_K=false` unless your server supports it.
