"""Run Asi Bench via BenchFlow — converts tasks if needed, then evaluates."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _load_converter():
    spec = importlib.util.spec_from_file_location(
        "_bf_asi-bench_converter", _HERE / "benchflow.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ensure_converted_tasks() -> Path:
    """Convert the source benchmark into BenchFlow tasks under ``tasks/``."""
    converter = _load_converter()
    source_dir = _HERE / "source"
    output_dir = _HERE / "tasks"
    converter.convert_all(source_dir, output_dir)
    return output_dir


async def main() -> None:
    from benchflow.evaluation import Evaluation

    tasks_dir = ensure_converted_tasks()
    job = Evaluation.from_yaml(str(_HERE / "asi-bench.yaml"))
    job._tasks_dir = tasks_dir  # type: ignore[attr-defined]
    result = await job.run()
    print(f"Score: {result.passed}/{result.total} ({result.score:.1%})")


if __name__ == "__main__":
    asyncio.run(main())
