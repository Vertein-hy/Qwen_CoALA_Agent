param(
  [ValidateSet("cpu-x64", "cuda-12.4-x64", "cuda-13.1-x64", "vulkan-x64")]
  [string]$Variant = "cpu-x64",
  [string]$ReleaseTag = ""
)

$ErrorActionPreference = "Stop"

# Install prebuilt llama.cpp binaries on Windows (no local compilation).
# Usage:
# powershell -ExecutionPolicy Bypass -File .\scripts\install_llama_prebuilt_windows.ps1 -Variant cpu-x64

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "python not found in PATH."
}

$RootDir = (Resolve-Path "$PSScriptRoot\..").Path
$TargetDir = Join-Path $RootDir "third_party\llama.cpp\build\bin\Release"
$DownloadDir = Join-Path $RootDir "third_party\llama.cpp\prebuilt"
New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
New-Item -ItemType Directory -Force -Path $DownloadDir | Out-Null

$PatternMap = @{
  "cpu-x64"       = "^llama-.*-bin-win-cpu-x64\.zip$"
  "cuda-12.4-x64" = "^cudart-llama-bin-win-cuda-12\.4-x64\.zip$|^llama-.*-bin-win-cuda-12\.4-x64\.zip$"
  "cuda-13.1-x64" = "^cudart-llama-bin-win-cuda-13\.1-x64\.zip$|^llama-.*-bin-win-cuda-13\.1-x64\.zip$"
  "vulkan-x64"    = "^llama-.*-bin-win-vulkan-x64\.zip$"
}

function Test-ZipIntegrity([string]$ZipPath) {
  if (-not (Test-Path $ZipPath)) {
    return $false
  }
  try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $z = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path $ZipPath))
    $null = $z.Entries.Count
    $z.Dispose()
    return $true
  } catch {
    return $false
  }
}

function Get-AssetFromApi([string]$RegexPattern) {
  $Py = @"
import json
import re
import requests

variant_pattern = r'''$RegexPattern'''
api = 'https://api.github.com/repos/ggml-org/llama.cpp/releases/latest'
r = requests.get(api, headers={'User-Agent': 'coala-agent'}, timeout=30)
r.raise_for_status()
release = r.json()
tag = release.get('tag_name', 'latest')
assets = release.get('assets', [])
target = None
for a in assets:
    name = a.get('name', '')
    if re.match(variant_pattern, name):
        target = (name, a.get('browser_download_url'))
        break
if not target:
    raise SystemExit('No matching prebuilt asset found for variant.')
print(json.dumps({'tag': tag, 'name': target[0], 'url': target[1]}))
"@
  return ($Py | python -)
}

function Get-AssetFromTag([string]$Tag, [string]$VariantName) {
  switch ($VariantName) {
    "cpu-x64"       { $name = "llama-$Tag-bin-win-cpu-x64.zip" }
    "cuda-12.4-x64" { $name = "cudart-llama-bin-win-cuda-12.4-x64.zip" }
    "cuda-13.1-x64" { $name = "cudart-llama-bin-win-cuda-13.1-x64.zip" }
    "vulkan-x64"    { $name = "llama-$Tag-bin-win-vulkan-x64.zip" }
    default         { throw "Unsupported variant: $VariantName" }
  }
  $url = "https://github.com/ggml-org/llama.cpp/releases/download/$Tag/$name"
  return [PSCustomObject]@{ tag = $Tag; name = $name; url = $url }
}

$Pattern = $PatternMap[$Variant]
if ($ReleaseTag) {
  $AssetInfo = Get-AssetFromTag -Tag $ReleaseTag -VariantName $Variant
} else {
  $AssetInfoJson = Get-AssetFromApi -RegexPattern $Pattern
  $AssetInfo = $AssetInfoJson | ConvertFrom-Json
}

Write-Host "[info] release=$($AssetInfo.tag)"
Write-Host "[info] asset=$($AssetInfo.name)"

$ZipPath = Join-Path $DownloadDir $AssetInfo.name
if (-not (Test-ZipIntegrity $ZipPath)) {
  if (Test-Path $ZipPath) {
    Write-Host "[warn] Existing zip is broken. Re-downloading."
    Remove-Item -Force $ZipPath
  }

  Write-Host "[download] $($AssetInfo.url)"
  $PyDownload = @"
import requests
from pathlib import Path

url = r'''$($AssetInfo.url)'''
path = Path(r'''$ZipPath''')
path.parent.mkdir(parents=True, exist_ok=True)
with requests.get(url, stream=True, timeout=60) as r:
    r.raise_for_status()
    expected = int(r.headers.get('Content-Length', '0') or 0)
    written = 0
    with path.open('wb') as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
                written += len(chunk)
if expected and written != expected:
    raise SystemExit(f'incomplete download: expected={expected} written={written}')
print(path)
"@
  $PyDownload | python -
}

if (-not (Test-ZipIntegrity $ZipPath)) {
  throw "Downloaded zip is still invalid: $ZipPath"
}

$ExtractDir = Join-Path $DownloadDir ([System.IO.Path]::GetFileNameWithoutExtension($AssetInfo.name))
if (Test-Path $ExtractDir) {
  Remove-Item -Recurse -Force $ExtractDir
}
Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force

$ServerExe = Get-ChildItem -Path $ExtractDir -Recurse -File -Filter "llama-server.exe" |
  Select-Object -First 1
if (-not $ServerExe) {
  throw "llama-server.exe not found in extracted package."
}

$SourceBinDir = $ServerExe.Directory.FullName
Copy-Item -Path (Join-Path $SourceBinDir "*") -Destination $TargetDir -Force

$Installed = Join-Path $TargetDir "llama-server.exe"
if (-not (Test-Path $Installed)) {
  throw "Install failed: llama-server.exe not found at $Installed"
}

Write-Host "[done] Installed prebuilt llama binaries to:"
Write-Host "       $TargetDir"
Write-Host "[next] Run:"
Write-Host "       powershell -ExecutionPolicy Bypass -File .\scripts\run_llama_server_windows.ps1 -ModelPath \"models/gguf/unsloth-qwen3.5-9b/Qwen3.5-9B-UD-Q4_K_XL.gguf\""
