#!/usr/bin/env python3
"""ASI-Bench BenchFlow verifier: staging, scoring, and reward reporting.

Invoked by test.sh inside the BenchFlow sandbox after the agent finishes.
Reads from /verifier/ (reference, evaluator code, instance.json, output_specs.json)
and /workspace/ (agent outputs), writes to /logs/verifier/.

Contract:
  - Submission failure (missing/bad outputs): write reward (may be 0.0), exit 0.
  - Evaluator/infrastructure error: do NOT write reward, write asi_error.json, exit 1.
    BenchFlow records this as verifier_failure, not a 0-score.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

# ── layout constants ────────────────────────────────────────────────────────

VERIFIER_DIR = Path("/verifier")
WORKSPACE_DIR = Path("/workspace")
LOGS_DIR = Path("/logs/verifier")

EVALUATOR_DIR = VERIFIER_DIR / "evaluator"
REFERENCE_DIR = VERIFIER_DIR / "reference"
INSTANCE_JSON = VERIFIER_DIR / "instance.json"
OUTPUT_SPECS_JSON = VERIFIER_DIR / "output_specs.json"
SCORE_DIVISOR_JSON = VERIFIER_DIR / "score_divisor.json"


# ── path safety ─────────────────────────────────────────────────────────────

def _safe_rel(value: str) -> Path:
    """Reject absolute paths, traversal, and null bytes."""
    if not value or value.startswith("/") or "\\" in value or "\x00" in value:
        raise ValueError(f"unsafe output path: {value!r}")
    parts = value.split("/")
    if any(p in ("", "..") for p in parts):
        raise ValueError(f"unsafe output path: {value!r}")
    return Path(value)


def _is_safe_regular(path: Path) -> bool:
    """Return True iff path is a regular file (not a symlink)."""
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── output staging ──────────────────────────────────────────────────────────

def _stage_outputs(
    workspace: Path,
    output_specs: list[dict],
    staging: Path,
) -> dict[str, str]:
    """Copy declared output files from workspace into staging/.

    Returns a dict mapping relative output path → SHA-256 for present files.
    Missing files are noted in the return value with None-like absence
    (they are not copied) and will be caught by gates/scorers.
    """
    present: dict[str, str] = {}
    for spec in output_specs:
        rel_str = spec.get("name", "")
        if not rel_str:
            continue
        try:
            rel = _safe_rel(rel_str)
        except ValueError:
            continue  # invalid spec → skip, scorer will fail

        src = workspace / rel
        if src.is_symlink():
            # Reject symlinks; scorer will see the file missing
            continue
        if not src.is_file():
            continue  # missing; scorer handles it as submission failure

        dst = staging / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        present[rel_str] = _sha256(dst)
    return present


def _stage_data_inputs(evaluator_dir: Path, staging: Path) -> None:
    """Copy instance data/ from the evaluator bundle into staging/ for scorers."""
    # Some scorers need the original data/ directory alongside predictions.
    # It lives in the evaluator dir, placed there by the converter.
    data_src = evaluator_dir / "data"
    if data_src.is_dir():
        data_dst = staging / "data"
        if not data_dst.exists():
            shutil.copytree(data_src, data_dst, symlinks=False)


# ── evaluator bootstrap ──────────────────────────────────────────────────────

def _bootstrap_evaluator(evaluator_dir: Path) -> None:
    """Prepend evaluator_dir to sys.path so ai4sci_bench imports cleanly.

    Also wires the task_eval.yaml path into the evaluator environment so
    resolve_task_sources() finds it without needing a git checkout.
    """
    ev = str(evaluator_dir.resolve())
    if ev not in sys.path:
        sys.path.insert(0, ev)


# ── scoring ──────────────────────────────────────────────────────────────────

def _load_instance() -> dict[str, Any]:
    if not INSTANCE_JSON.is_file():
        raise FileNotFoundError(f"instance.json not found at {INSTANCE_JSON}")
    with INSTANCE_JSON.open(encoding="utf-8") as fh:
        return json.load(fh)


def _load_output_specs() -> list[dict]:
    if not OUTPUT_SPECS_JSON.is_file():
        return []
    with OUTPUT_SPECS_JSON.open(encoding="utf-8") as fh:
        return json.load(fh)


def _load_score_divisor() -> float:
    if not SCORE_DIVISOR_JSON.is_file():
        return 1.0
    with SCORE_DIVISOR_JSON.open(encoding="utf-8") as fh:
        data = json.load(fh)
    divisor = float(data.get("score_divisor", 1.0))
    return divisor if divisor > 0 else 1.0


def _run_scoring(
    evaluator_dir: Path,
    pred_dir: Path,
    ref_dir: Path,
    instance: dict,
) -> dict[str, Any]:
    """Import and call the ASI scoring framework.

    Returns a dict with at minimum:
      final_score, max_score, hard_gates_passed,
      gate_results, score_results, scorer_internal_error (bool)
    """
    import importlib

    # Load task evaluation config
    task_eval_path = evaluator_dir / "task_eval.yaml"
    if not task_eval_path.is_file():
        raise FileNotFoundError(f"task_eval.yaml not found in {evaluator_dir}")

    import yaml
    with task_eval_path.open(encoding="utf-8") as fh:
        task_eval: dict = yaml.safe_load(fh) or {}

    evaluation = task_eval.get("evaluation") or {}

    # Register scorers
    scorer_mod = importlib.import_module("ai4sci_bench.core.scorer")
    scorers_pkg = evaluator_dir / "ai4sci_bench" / "scorers"
    for scorer_file in sorted(scorers_pkg.glob("*.py")):
        if not scorer_file.stem.startswith("_") and scorer_file.stem != "custom":
            importlib.import_module(f"ai4sci_bench.scorers.{scorer_file.stem}")

    # Load custom scorer if present
    custom_path = evaluator_dir / "custom_scorer.py"
    if custom_path.is_file():
        custom_mod = importlib.import_module("ai4sci_bench.scorers.custom")
        custom_mod.load_custom_scorer(evaluator_dir)

    # Load the core evaluation function
    core = importlib.import_module("ai4sci_bench.core.task")
    evaluate_fn = getattr(core, "_evaluate_gates_and_scores", None)
    if evaluate_fn is None:
        # Try alternate import path used in older revisions
        scoring_mod = importlib.import_module("scoring")
        evaluate_fn = scoring_mod._evaluate_gates_and_scores

    params = instance.get("parameters") or {}
    prompt_level = instance.get("prompt_level", "B1").upper()

    result = evaluate_fn(evaluation, pred_dir, ref_dir, params, prompt_level)
    return result


# ── reward normalization ─────────────────────────────────────────────────────

def _normalize_reward(
    result: dict[str, Any],
    score_divisor: float,
) -> float:
    """Compute [0,1] reward from ASI scoring result."""
    final_score = float(result.get("final_score") or 0.0)
    max_score = float(result.get("max_score") or 0.0)

    # score_divisor overrides max_score when set (e.g. ising: 1.05)
    effective_max = score_divisor if score_divisor != 1.0 else max(max_score, 1.0)

    reward = final_score / effective_max
    return max(0.0, min(1.0, reward))


# ── output writers ───────────────────────────────────────────────────────────

def _write_reward(reward: float, result: dict, instance: dict, artifact_shas: dict[str, str]) -> None:
    """Write reward.txt and reward.json to /logs/verifier/."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # reward.txt — plain scalar
    (LOGS_DIR / "reward.txt").write_text(f"{reward:.10f}\n", encoding="utf-8")

    # reward.json — BenchFlow format: scalar reward + metadata/details
    # Flat non-[0,1] fields are rejected by BenchFlow → put everything in metadata/details
    reward_json = {
        "reward": reward,
        "metadata": {
            "benchmark": "ASI-Bench",
            "seed": 31415,
            "official": False,
            "task_id": instance.get("task_id"),
            "instance_id": instance.get("instance_id"),
            "prompt_level": instance.get("prompt_level"),
            "asi_revision": instance.get("asi_revision"),
            "hf_revision": instance.get("hf_revision"),
            "final_score": result.get("final_score"),
            "max_score": result.get("max_score"),
            "score_divisor": result.get("score_divisor", 1.0),
        },
        "details": {
            "hard_gates_passed": result.get("hard_gates_passed", False),
            "gate_results": result.get("gate_results") or [],
            "score_results": result.get("score_results") or [],
        },
        "artifacts": {path: sha for path, sha in artifact_shas.items()},
    }
    (LOGS_DIR / "reward.json").write_text(
        json.dumps(reward_json, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # asi_score.json — full detail without BenchFlow schema restrictions
    asi_json = dict(reward_json)
    asi_json["scorer_internal_error"] = result.get("scorer_internal_error", False)
    (LOGS_DIR / "asi_score.json").write_text(
        json.dumps(asi_json, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_error(exc: Exception, context: str) -> None:
    """Write asi_error.json (no reward) for infrastructure failures."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    error_doc = {
        "scorer_internal_error": True,
        "error_type": type(exc).__name__,
        "error_context": context,
        "detail": traceback.format_exc(),
    }
    (LOGS_DIR / "asi_error.json").write_text(
        json.dumps(error_doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    # Explicitly ensure no reward files are present
    for name in ("reward.txt", "reward.json"):
        p = LOGS_DIR / name
        if p.exists():
            p.unlink()


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    # 1. Load metadata (evaluator-infrastructure failures → exit 1, no reward)
    try:
        instance = _load_instance()
        output_specs = _load_output_specs()
        score_divisor = _load_score_divisor()
    except Exception as exc:
        _write_error(exc, "loading instance metadata")
        print(f"[verifier] evaluator error (metadata): {exc}", file=sys.stderr)
        return 1

    # 2. Validate seed (fail-closed)
    if instance.get("seed") != 31415:
        exc = ValueError(f"Unsupported seed: {instance.get('seed')!r}; only seed31415 is supported")
        _write_error(exc, "seed validation")
        print(f"[verifier] evaluator error (seed): {exc}", file=sys.stderr)
        return 1

    # 3. Bootstrap evaluator sys.path
    try:
        _bootstrap_evaluator(EVALUATOR_DIR)
    except Exception as exc:
        _write_error(exc, "evaluator bootstrap")
        print(f"[verifier] evaluator error (bootstrap): {exc}", file=sys.stderr)
        return 1

    # 4. Stage outputs in a temp directory
    staging = Path(tempfile.mkdtemp(prefix="asi-verifier-"))
    try:
        artifact_shas = _stage_outputs(WORKSPACE_DIR, output_specs, staging)
        _stage_data_inputs(EVALUATOR_DIR, staging)

        # 5. Run scoring
        try:
            result = _run_scoring(EVALUATOR_DIR, staging, REFERENCE_DIR, instance)
        except Exception as exc:
            # Distinguish evaluator crash from submission failure
            internal = getattr(exc, "scorer_internal_error", False)
            if internal or isinstance(exc, (ImportError, FileNotFoundError, AttributeError)):
                _write_error(exc, "evaluator scoring")
                print(f"[verifier] evaluator error (scoring): {exc}", file=sys.stderr)
                return 1
            # Treat as submission failure: score 0, exit 0
            result = {
                "final_score": 0.0,
                "max_score": 1.0,
                "hard_gates_passed": False,
                "gate_results": [],
                "score_results": [],
                "scorer_internal_error": False,
                "submission_failure": str(exc),
            }

        # Check for internal error flag from the scorer itself
        if result.get("scorer_internal_error"):
            exc = RuntimeError(
                f"Scorer reported internal error: {result.get('error_detail', 'unknown')}"
            )
            _write_error(exc, "scorer_internal_error flag")
            print(f"[verifier] evaluator error (internal flag): {exc}", file=sys.stderr)
            return 1

        # 6. Normalize reward
        reward = _normalize_reward(result, score_divisor)

        # 7. Write outputs (submission result → exit 0)
        _write_reward(reward, result, instance, artifact_shas)
        print(f"[verifier] reward={reward:.6f}", file=sys.stdout)
        return 0

    except Exception as exc:
        _write_error(exc, "verifier outer")
        print(f"[verifier] evaluator error (outer): {exc}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
