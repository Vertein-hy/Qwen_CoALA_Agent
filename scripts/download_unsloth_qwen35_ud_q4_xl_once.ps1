param(
  [string]$Endpoint = "https://hf-mirror.com",
  [string]$RepoId = "unsloth/Qwen3.5-9B-GGUF",
  [string]$OutputDir = "models/gguf/unsloth-qwen3.5-9b",
  [int]$Workers = 2,
  [switch]$IncludeMmproj
)

$ErrorActionPreference = "Stop"

# One-shot download script for:
# - unsloth/Qwen3.5-9B-GGUF
# - UD-Q4_K_XL quantization
#
# Usage:
# powershell -ExecutionPolicy Bypass -File .\scripts\download_unsloth_qwen35_ud_q4_xl_once.ps1
#
# Optional (include mmproj):
# powershell -ExecutionPolicy Bypass -File .\scripts\download_unsloth_qwen35_ud_q4_xl_once.ps1 -IncludeMmproj

$RootDir = (Resolve-Path "$PSScriptRoot\..").Path
$Downloader = Join-Path $RootDir "scripts\download_hf_model.py"

if (-not (Test-Path $Downloader)) {
  throw "Required downloader not found: $Downloader"
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "python is not found in PATH."
}

# Force domestic mirror and disable xet path (more stable behind proxies).
$env:HF_ENDPOINT = $Endpoint
$env:HF_HUB_DISABLE_XET = "1"

Write-Host "[info] HF_ENDPOINT=$($env:HF_ENDPOINT)"
Write-Host "[info] RepoId=$RepoId"
Write-Host "[info] OutputDir=$OutputDir"
Write-Host "[info] Target pattern=*UD-Q4_K_XL*.gguf"
if ($IncludeMmproj) {
  Write-Host "[info] Also downloading mmproj-F16.gguf"
}

$ArgsList = @(
  $Downloader,
  "--repo-id", $RepoId,
  "--local-dir", $OutputDir,
  "--endpoint", $Endpoint,
  "--workers", "$Workers",
  "--retries", "5",
  "--etag-timeout", "60",
  "--disable-xet",
  "--include", "*UD-Q4_K_XL*.gguf"
)

if ($IncludeMmproj) {
  $ArgsList += @("--include", "mmproj-F16.gguf")
}

& python @ArgsList
if ($LASTEXITCODE -ne 0) {
  throw "Download failed with exit code: $LASTEXITCODE"
}

Write-Host ""
Write-Host "[done] Download completed. Files:"
Get-ChildItem -Path $OutputDir -File -ErrorAction SilentlyContinue |
  Sort-Object Length -Descending |
  Select-Object Name, Length,
  @{Name = "SizeGB"; Expression = { [math]::Round($_.Length / 1GB, 3) }} |
  Format-Table -AutoSize
