# Dev Bundle Mirror Interface (Draft)

Goal: pull a ready-to-run package for each OS so development can resume from any machine with minimal setup.

## 1) Bundle strategy

Each bundle is immutable and versioned:

- `coala-devbundle-{version}-{os}-{arch}.zip`
- examples:
  - `coala-devbundle-2026.03.09-win-x64.zip`
  - `coala-devbundle-2026.03.09-macos-arm64.zip`

Bundle contents:

- project snapshot (`core/`, `modules/`, `memory/`, `scripts/`, `docs/`)
- locked deps metadata (`requirements.txt`, optional wheelhouse)
- model runtime assets:
  - GGUF file(s)
  - llama.cpp binaries for target OS (optional split package)
- resume metadata:
  - `manifest.json`
  - `state/checkpoints.json`
  - checksums (`SHA256SUMS`)

## 2) Mirror API (minimal)

Base URL example: `https://mirror.example.com/api/v1`

Endpoints:

1. `GET /bundles`
- query: `os`, `arch`, `channel` (`stable|nightly`)
- return: available bundle list + hash + size + created_at

2. `GET /bundles/{bundle_id}/manifest`
- return: file list, hash list, required env, compatible model aliases

3. `GET /bundles/{bundle_id}/download`
- supports HTTP range for resume

4. `POST /bundles/resolve`
- body: `{ os, arch, gpu_vendor, prefer_quant }`
- return: recommended bundle id and startup command

## 3) Client flow

1. Detect local platform (`os/arch/gpu`).
2. Call `POST /bundles/resolve`.
3. Download bundle with resume + checksum verification.
4. Unpack to workspace.
5. Run post-install bootstrap script:
   - Windows: `scripts/bootstrap_windows.ps1`
   - macOS: `scripts/bootstrap_mac.sh`
6. Start local model endpoint and app.

## 4) Compatibility contract

`manifest.json` should include:

- `bundle_id`
- `git_commit`
- `python_version`
- `llama_cpp_version`
- `model_alias_map` (e.g. `Qwen/Qwen3.5-9B -> qwen-local-gguf`)
- `entrypoints` (commands for each OS)
- `min_disk_gb`, `min_ram_gb`

## 5) Storage and distribution

- Store artifacts in object storage (S3/OSS/MinIO).
- Put CDN in front for global acceleration.
- Keep metadata in a small DB table or static index JSON.
- Sign manifests (optional) for integrity and supply-chain trust.

## 6) First implementation target

Phase 1 (1-2 days):

- static index JSON + downloadable zip files
- checksum verify + resumable download
- one bundle per OS (win-x64, macos-arm64)

Phase 2:

- `/resolve` recommendation API
- incremental patch bundles (delta updates)
- multi-model bundle channels (`base`, `dev`, `full`)
