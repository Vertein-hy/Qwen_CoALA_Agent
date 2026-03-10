#!/usr/bin/env python3
"""Download a Hugging Face model with visible per-file progress.

This script is designed for slow/proxied networks where snapshot_download
looks "stuck" with no visible output.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

from huggingface_hub import HfApi, hf_hub_download


def _fmt_bytes(num: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{num} B"


def _filter_files(
    names: Iterable[str],
    include: list[str],
    exclude: list[str],
) -> list[str]:
    selected: list[str] = []
    for name in names:
        if include and not any(fnmatch.fnmatch(name, p) for p in include):
            continue
        if exclude and any(fnmatch.fnmatch(name, p) for p in exclude):
            continue
        selected.append(name)
    return selected


def _local_size(local_dir: Path, rel_path: str) -> int:
    path = local_dir / rel_path
    return path.stat().st_size if path.exists() else 0


def _download_one(
    *,
    repo_id: str,
    filename: str,
    revision: str,
    endpoint: str | None,
    token: str | None,
    local_dir: Path,
    force_download: bool,
    max_retries: int,
    etag_timeout: float,
) -> tuple[str, int, float]:
    last_error: Exception | None = None
    begin = time.time()
    for attempt in range(1, max_retries + 1):
        try:
            path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                revision=revision,
                endpoint=endpoint,
                token=token,
                local_dir=str(local_dir),
                force_download=force_download,
                etag_timeout=etag_timeout,
            )
            size = Path(path).stat().st_size if Path(path).exists() else 0
            return filename, size, time.time() - begin
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == max_retries:
                break
            wait_s = min(8, attempt * 2)
            print(
                f"[retry] {filename} attempt={attempt}/{max_retries} "
                f"wait={wait_s}s err={exc}",
                flush=True,
            )
            time.sleep(wait_s)
    assert last_error is not None
    raise last_error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-id", default="Qwen/Qwen3.5-9B")
    parser.add_argument("--revision", default="main")
    parser.add_argument("--local-dir", default="models/hf/Qwen3.5-9B")
    parser.add_argument(
        "--endpoint",
        default=os.getenv("HF_ENDPOINT", "").strip() or None,
        help="Example: https://hf-mirror.com",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("HF_TOKEN", "").strip() or None,
        help="HF token, optional for public repos.",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--etag-timeout", type=float, default=30.0)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument(
        "--disable-xet",
        action="store_true",
        help="Set HF_HUB_DISABLE_XET=1 to avoid xet path if needed.",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        help="Glob pattern to include. Repeatable.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Glob pattern to exclude. Repeatable.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only list target files and local existence.",
    )
    args = parser.parse_args()

    if args.disable_xet:
        os.environ["HF_HUB_DISABLE_XET"] = "1"

    local_dir = Path(args.local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    api = HfApi(endpoint=args.endpoint, token=args.token)
    info = api.model_info(repo_id=args.repo_id, revision=args.revision)
    remote_files = [s.rfilename for s in info.siblings if s.rfilename]
    target_files = _filter_files(remote_files, args.include, args.exclude)
    target_files.sort()

    print(
        f"repo={args.repo_id} revision={args.revision} endpoint={args.endpoint or 'default'}",
        flush=True,
    )
    print(f"target_files={len(target_files)} local_dir={local_dir}", flush=True)

    existing = 0
    for name in target_files:
        if (local_dir / name).exists():
            existing += 1
    print(f"already_present={existing}/{len(target_files)}", flush=True)

    if args.check_only:
        for name in target_files:
            status = "ok" if (local_dir / name).exists() else "missing"
            size = _local_size(local_dir, name)
            print(f"[{status}] {name} ({_fmt_bytes(size)})")
        return 0

    done = 0
    total = len(target_files)
    start = time.time()
    total_bytes = 0

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(
                _download_one,
                repo_id=args.repo_id,
                filename=name,
                revision=args.revision,
                endpoint=args.endpoint,
                token=args.token,
                local_dir=local_dir,
                force_download=args.force_download,
                max_retries=max(1, args.retries),
                etag_timeout=args.etag_timeout,
            ): name
            for name in target_files
        }

        for future in as_completed(futures):
            name = futures[future]
            try:
                _, size, elapsed = future.result()
                done += 1
                total_bytes += size
                print(
                    f"[{done}/{total}] ok {name} "
                    f"size={_fmt_bytes(size)} elapsed={elapsed:.1f}s",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[{done}/{total}] failed {name} err={exc}", flush=True)
                return 2

    all_elapsed = time.time() - start
    print(
        f"done files={done}/{total} downloaded={_fmt_bytes(total_bytes)} "
        f"elapsed={all_elapsed:.1f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
