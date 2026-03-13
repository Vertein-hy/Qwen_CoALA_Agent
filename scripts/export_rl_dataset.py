"""Export decision-layer RL samples from saved trace payloads."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rl.decision_dataset import export_trace_dataset, load_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Input JSONL file containing trace payloads.")
    parser.add_argument("--output", required=True, help="Output JSONL file for RL decision samples.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    traces = load_jsonl(input_path)
    count = export_trace_dataset(traces, output_path)
    print(f"Exported {count} RL samples to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
