#!/usr/bin/env python3
"""Build SFT dataset from scored candidate trajectories."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def _score_of(row: dict) -> float:
    scores = row.get("scores", {})
    return float(scores.get("R_total", scores.get("total", 0.0)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/training/teacher_distilled.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/training/sft_dataset.jsonl"),
    )
    parser.add_argument("--top-k", type=int, default=2)
    args = parser.parse_args()

    rows: list[dict] = []
    for raw in args.input.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            rows.append(json.loads(raw))

    by_task: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_task[row.get("task_id", "unknown")].append(row)

    picked: list[dict] = []
    valid_count = 0
    for task_id, candidates in by_task.items():
        ranked = sorted(candidates, key=_score_of, reverse=True)
        for row in ranked[: args.top_k]:
            out = str(row.get("output", ""))
            is_valid = bool(out) and ("Final Answer:" in out)
            if is_valid:
                valid_count += 1
            picked.append(
                {
                    "task_id": task_id,
                    "trace_id": row.get("trace_id"),
                    "input": row.get("input", ""),
                    "output": out,
                    "trajectory": row.get("trajectory", []),
                    "scores": row.get("scores", {}),
                    "meta": {
                        **row.get("meta", {}),
                        "dataset": "sft",
                        "format_valid": is_valid,
                    },
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for row in picked:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    valid_rate = (valid_count / len(picked) * 100.0) if picked else 0.0
    print(
        f"input={len(rows)} tasks={len(by_task)} selected={len(picked)} "
        f"format_valid_rate={valid_rate:.2f}% output={args.output}"
    )


if __name__ == "__main__":
    main()
