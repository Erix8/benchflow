"""ASI-Bench to BenchFlow conversion boundary.

This module is the deliberately incomplete integration scaffold.  It defines the
source contract and the public converter entry points without downloading ASI-
Bench data or embedding benchmark scoring code.  The implementation must remain
fail-closed until the pinned ASI and Hugging Face revisions have been selected.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

# These placeholders are intentionally not revisions.  A real converter must
# replace both values together with immutable 40-character revisions.
ASI_REVISION = "REPLACE_WITH_40_CHARACTER_ASI_REVISION"
HF_REVISION = "REPLACE_WITH_IMMUTABLE_HF_DATASET_REVISION"
SUPPORTED_SEED = 31415
PROMPT_LEVELS = ("B1", "B2", "B3", "B4")


@dataclass(frozen=True)
class ASIBenchSource:
    """A fully materialized, pinned ASI-Bench source checkout."""

    source_dir: Path
    asi_revision: str = ASI_REVISION
    hf_revision: str = HF_REVISION


@dataclass(frozen=True)
class ASIBenchInstance:
    """One materialized seed31415 instance selected for conversion."""

    task_id: str
    instance_id: str
    prompt_level: str
    seed: int
    instance_dir: Path
    task_bundle_dir: Path


def validate_instance(instance: ASIBenchInstance) -> None:
    """Validate the non-negotiable public conversion boundary.

    This lightweight validator is usable by the eventual converter and keeps
    seed42, unknown seeds, and malformed prompt levels from being accepted by
    accident.  It does not read or generate reference data.
    """
    if instance.seed != SUPPORTED_SEED:
        raise ValueError(
            f"ASI-Bench BenchFlow integration only supports seed {SUPPORTED_SEED}; "
            f"got {instance.seed}"
        )
    if instance.prompt_level not in PROMPT_LEVELS:
        raise ValueError(
            f"prompt_level must be one of {PROMPT_LEVELS}; "
            f"got {instance.prompt_level!r}"
        )
    if not instance.instance_id:
        raise ValueError("instance_id must not be empty")
    if not instance.task_id:
        raise ValueError("task_id must not be empty")


def convert(
    source_instance: ASIBenchInstance,
    output_dir: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Convert one materialized source instance into a BenchFlow task.

    Conversion is intentionally unavailable in the scaffold.  In particular,
    this function must not silently create an empty task or a zero-reward
    verifier: missing implementation is an integration error, not a submission
    result.
    """
    del output_dir, overwrite
    validate_instance(source_instance)
    raise NotImplementedError(
        "ASI-Bench conversion is scaffold-only; source materialization and "
        "verifier integration are not implemented"
    )


def convert_all(
    source_dir: Path | None,
    output_dir: Path,
    *,
    overwrite: bool = False,
    limit: int | None = None,
    task_ids: list[str] | None = None,
    levels: list[str] | None = None,
) -> list[Path]:
    """Convert materialized ASI-Bench instances into task directories.

    The source directory is intentionally not inspected in this scaffold.  A
    future implementation must require pinned seed31415 material and reject
    network generation, seed42, and missing reference/task bundles.
    """
    del source_dir, output_dir, overwrite, limit, task_ids, levels
    raise NotImplementedError(
        "ASI-Bench source materialization is scaffold-only; no tasks were generated"
    )


def _parse_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    values = [item.strip() for item in value.split(",") if item.strip()]
    return values or None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert pinned seed31415 ASI-Bench material to BenchFlow tasks."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--task-ids", default=None, help="Comma-separated task IDs")
    parser.add_argument(
        "--levels",
        default=None,
        help="Comma-separated prompt levels (B1,B2,B3,B4)",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    convert_all(
        args.source_dir,
        args.output_dir,
        overwrite=args.overwrite,
        limit=args.limit,
        task_ids=_parse_csv(args.task_ids),
        levels=_parse_csv(args.levels),
    )


if __name__ == "__main__":
    main()
