"""Reserve the ASI-Bench execution and summary CLI surface.

The adapter is scaffold-only, so this command fails closed until task
materialization, verification, and ASI-compatible aggregation are implemented.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import NoReturn


class RunnerNotIntegratedError(RuntimeError):
    """Raised when a scaffold-only command is invoked."""


def run(tasks_dir: Path) -> NoReturn:
    """Run materialized ASI-Bench tasks once conversion is implemented."""
    raise RunnerNotIntegratedError(
        f"ASI-Bench execution is not integrated; cannot run tasks from {tasks_dir}"
    )


def summarize(jobs_dir: Path) -> NoReturn:
    """Produce ASI-compatible aggregation once result parsing is implemented."""
    raise RunnerNotIntegratedError(
        f"ASI-Bench summarization is not integrated; cannot read jobs from {jobs_dir}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or summarize ASI-Bench")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--tasks-dir", type=Path, required=True)

    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.add_argument("jobs_dir", type=Path)

    args = parser.parse_args()
    if args.command == "run":
        run(args.tasks_dir)
    else:
        summarize(args.jobs_dir)


if __name__ == "__main__":
    main()
