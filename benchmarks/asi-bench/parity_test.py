"""Parity validation for the Asi Bench -> BenchFlow conversion.

Run ``python benchmarks/asi-bench/parity_test.py --mode <full|eval-parity|side-by-side>``.
Each mode checks a parity layer (structural, eval, side-by-side). Faithful
translation must REPRODUCE the original's verdicts on identical inputs — record
the per-criterion ``original_verdict`` / ``adapted_verdict`` pairs in
``parity_experiment.json`` so ``bench eval adopt asi-bench --verify`` can score them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
PARITY_EXPERIMENT = _HERE / "parity_experiment.json"


def structural_parity(tasks_dir: Path) -> dict:
    """Step 3: assert every generated task has the required files + metadata."""
    raise NotImplementedError("Implement structural parity")


def eval_parity(tasks_dir: Path) -> dict:
    """Step 4: run the verifier on a known-good solution / dummy output."""
    raise NotImplementedError("Implement eval parity")


def side_by_side_parity(tasks_dir: Path) -> dict:
    """Step 5: compare per-criterion verdicts of original vs converted eval."""
    raise NotImplementedError("Implement side-by-side parity")


def main() -> None:
    parser = argparse.ArgumentParser(description="Asi Bench parity test")
    parser.add_argument(
        "--mode",
        choices=["full", "eval-parity", "side-by-side"],
        default="full",
    )
    parser.add_argument("--tasks-dir", type=Path, default=_HERE / "tasks")
    args = parser.parse_args()

    if args.mode == "eval-parity":
        result = eval_parity(args.tasks_dir)
    elif args.mode == "side-by-side":
        result = side_by_side_parity(args.tasks_dir)
    else:
        result = structural_parity(args.tasks_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
