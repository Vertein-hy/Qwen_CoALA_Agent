param(
  [Parameter(Mandatory = $true)]
  [string]$ModelPath
)

$ErrorActionPreference = "Stop"

# Usage:
# powershell -ExecutionPolicy Bypass -File .\scripts\run_llama_server_windows.ps1 -ModelPath "models/gguf/Qwen3.5-9B-Instruct-Q4_K_M.gguf"

$RootDir = (Resolve-Path "$PSScriptRoot\..").Path
$LlamaServer = Join-Path $RootDir "third_party\llama.cpp\build\bin\Release\llama-server.exe"

if (-not (Test-Path $LlamaServer)) {
  throw "llama-server.exe not found. Build llama.cpp first."
}

& $LlamaServer `
  -m $ModelPath `
  --host 127.0.0.1 `
  --port 8000 `
  --ctx-size 8192 `
  --alias qwen-local-gguf
