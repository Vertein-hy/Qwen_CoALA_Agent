param(
  [string]$ModelId = "Qwen/Qwen3.5-9B",
  [string]$Quant = "Q4_K_M"
)

$ErrorActionPreference = "Stop"

# Usage:
# powershell -ExecutionPolicy Bypass -File .\scripts\convert_qwen_to_gguf_windows.ps1 -ModelId "Qwen/Qwen3.5-9B" -Quant "Q4_K_M"
#
# This script:
# 1) downloads HF safetensors model
# 2) converts to f16 gguf
# 3) quantizes to target type

$RootDir = (Resolve-Path "$PSScriptRoot\..").Path
$HfDir = Join-Path $RootDir "models\hf"
$GgufDir = Join-Path $RootDir "models\gguf"
$ThirdPartyDir = Join-Path $RootDir "third_party"
$LlamaCppDir = Join-Path $ThirdPartyDir "llama.cpp"

New-Item -ItemType Directory -Force -Path $HfDir | Out-Null
New-Item -ItemType Directory -Force -Path $GgufDir | Out-Null
New-Item -ItemType Directory -Force -Path $ThirdPartyDir | Out-Null

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw "git is required but not found in PATH."
}
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
  throw "cmake is required but not found in PATH."
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "python is required but not found in PATH."
}
if (-not (Get-Command huggingface-cli -ErrorAction SilentlyContinue)) {
  throw "huggingface-cli is required but not found in PATH. Install via: pip install -U huggingface_hub"
}

if (-not (Test-Path $LlamaCppDir)) {
  git clone https://github.com/ggml-org/llama.cpp.git $LlamaCppDir
}

cmake -S $LlamaCppDir -B (Join-Path $LlamaCppDir "build")
cmake --build (Join-Path $LlamaCppDir "build") --config Release -j

$ModelName = ($ModelId -split "/")[-1]
$HfLocalPath = Join-Path $HfDir $ModelName
huggingface-cli download $ModelId --local-dir $HfLocalPath

$F16Out = Join-Path $GgufDir "$ModelName-f16.gguf"
python (Join-Path $LlamaCppDir "convert_hf_to_gguf.py") $HfLocalPath --outfile $F16Out --outtype f16

$QuantExeRelease = Join-Path $LlamaCppDir "build\bin\Release\llama-quantize.exe"
$QuantExeBin = Join-Path $LlamaCppDir "build\bin\llama-quantize.exe"
if (Test-Path $QuantExeRelease) {
  $QuantExe = $QuantExeRelease
} elseif (Test-Path $QuantExeBin) {
  $QuantExe = $QuantExeBin
} else {
  throw "llama-quantize.exe not found after build."
}

$QuantOut = Join-Path $GgufDir "$ModelName-$Quant.gguf"
& $QuantExe $F16Out $QuantOut $Quant

Write-Host "Done: $QuantOut"
