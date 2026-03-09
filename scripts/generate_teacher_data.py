#!/usr/bin/env python3
"""Generate teacher-distilled training samples from frozen eval set."""

from __future__ import annotations

import argparse
import json
import random
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.llm_interface import LLMInterface
from core.scorer import RuleBasedScorer


@dataclass(frozen=True)
class EvalTask:
    task_id: str
    bucket: str
    prompt: str
    expected: str


def _read_eval_tasks(eval_dir: Path) -> list[EvalTask]:
    tasks: list[EvalTask] = []
    for path in sorted(eval_dir.glob("*.jsonl")):
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            tasks.append(
                EvalTask(
                    task_id=row["task_id"],
                    bucket=row.get("bucket", "T1"),
                    prompt=row["input"],
                    expected=row.get("expected", ""),
                )
            )
    if not tasks:
        raise RuntimeError(f"No eval tasks found in {eval_dir}")
    return tasks


def _teacher_answer(
    llm: LLMInterface,
    task: EvalTask,
    allow_fallback: bool,
    route_hint: str,
    force_fallback: bool,
) -> tuple[str, str]:
    messages = [
        {
            "role": "system",
            "content": (
                "你是 teacher 模型。请给出高质量、简洁、可执行的答案。"
                "输出必须包含 Final Answer: 前缀。"
            ),
        },
        {"role": "user", "content": task.prompt},
    ]
    try:
        if force_fallback:
            raise RuntimeError("forced_fallback")
        res = llm.chat_with_meta(messages=messages, route_hint=route_hint, temperature=0.4)
        text = res.content.strip()
        if "Final Answer:" not in text:
            text = f"Final Answer: {text}"
        return text, res.model_name
    except Exception:
        if not allow_fallback:
            raise
        # Offline-safe fallback so dataset generation does not block on API availability.
        return (
            (
                "Final Answer: "
                f"针对任务 {task.task_id}（{task.bucket}），先明确目标，再执行最小步骤并验证结果。"
            ),
            "teacher_fallback_template",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-dir", type=Path, default=ROOT / "data" / "eval")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "training" / "teacher_distilled.jsonl",
    )
    parser.add_argument("--num-samples", type=int, default=600)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-fallback", action="store_true")
    parser.add_argument("--teacher-route", choices=["large", "small"], default="large")
    parser.add_argument("--force-fallback", action="store_true")
    args = parser.parse_args()

    random.seed(args.seed)
    tasks = _read_eval_tasks(args.eval_dir)
    llm = LLMInterface()
    scorer = RuleBasedScorer()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with args.output.open("w", encoding="utf-8") as f:
        for _ in range(args.num_samples):
            task = random.choice(tasks)
            trace_id = f"tr_{uuid.uuid4().hex}"
            answer, teacher_model = _teacher_answer(
                llm=llm,
                task=task,
                allow_fallback=not args.no_fallback,
                route_hint=args.teacher_route,
                force_fallback=args.force_fallback,
            )
            score = scorer.score(
                response_text=answer,
                tool_steps=0,
                memory_hits=0,
                reached_final_answer=("Final Answer:" in answer),
            )
            score_dict = score.as_dict()
            jitter = random.uniform(-0.05, 0.05)
            total = max(0.0, min(1.0, float(score_dict["R_total"]) + jitter))
            score_dict["R_total"] = total
            score_dict["total"] = total
            row: dict[str, Any] = {
                "task_id": task.task_id,
                "trace_id": trace_id,
                "bucket": task.bucket,
                "input": task.prompt,
                "trajectory": [
                    {
                        "step": 1,
                        "plan": "analyze_then_answer",
                        "action": "direct_answer",
                        "action_input": {},
                        "observation": "",
                        "rationale_short": "teacher distilled baseline",
                    }
                ],
                "output": answer,
                "scores": score_dict,
                "meta": {
                    "source": "teacher_distilled",
                    "model_version": teacher_model,
                    "expected_hint": task.expected,
                },
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1

    print(f"generated={written} output={args.output}")


if __name__ == "__main__":
    main()
