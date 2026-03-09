#!/usr/bin/env python3
"""Build DPO chosen/rejected pairs from scored candidates."""

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
        default=Path("data/training/dpo_pairs.jsonl"),
    )
    parser.add_argument("--min-score-gap", type=float, default=0.2)
    args = parser.parse_args()

    rows: list[dict] = []
    for raw in args.input.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            rows.append(json.loads(raw))

    by_task: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_task[row.get("task_id", "unknown")].append(row)

    pairs: list[dict] = []
    for task_id, candidates in by_task.items():
        if len(candidates) < 2:
            continue
        ranked = sorted(candidates, key=_score_of, reverse=True)
        chosen = ranked[0]
        rejected = ranked[-1]
        gap = _score_of(chosen) - _score_of(rejected)
        if gap < args.min_score_gap:
            continue
        pairs.append(
            {
                "task_id": task_id,
                "trace_id_chosen": chosen.get("trace_id"),
                "trace_id_rejected": rejected.get("trace_id"),
                "input": chosen.get("input", ""),
                "chosen": chosen.get("output", ""),
                "rejected": rejected.get("output", ""),
                "score_chosen": _score_of(chosen),
                "score_rejected": _score_of(rejected),
                "score_gap": gap,
                "meta": {"dataset": "dpo", "source": "auto_scored"},
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for row in pairs:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(
        f"input={len(rows)} tasks={len(by_task)} pairs={len(pairs)} "
        f"min_score_gap={args.min_score_gap} output={args.output}"
    )


if __name__ == "__main__":
    main()
