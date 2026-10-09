"""Contract tests for the ASI-Bench integration.

These tests cover the converter boundary and verifier contract.  They do not
run BenchFlow, download source material, or claim scoring parity.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
ADAPTER = ROOT / "benchmarks" / "asi-bench"


def _load_adapter():
    spec = importlib.util.spec_from_file_location(
        "asi_bench_benchflow", ADAPTER / "benchflow.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_scaffold_has_planned_public_files_and_no_materialized_tasks() -> None:
    expected = {
        "__init__.py",
        "benchflow.py",
        "main.py",
        "parity_test.py",
        "run_asi_bench.py",
        "asi-bench.yaml",
        "benchmark.yaml",
        "parity_experiment.json",
        "README.md",
        "verifier_template/test.sh",
        "verifier_template/score_entry.py",
    }
    actual = {
        str(path.relative_to(ADAPTER))
        for path in ADAPTER.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert expected <= actual
    assert not (ADAPTER / "tasks").exists()
    assert not (ADAPTER / "source").exists()
    assert not any(
        path.name in {"generate_gt.py", "precompute_gt.py"}
        for path in ADAPTER.rglob("*")
    )


def test_descriptor_and_parity_are_explicitly_incomplete() -> None:
    descriptor = yaml.safe_load((ADAPTER / "benchmark.yaml").read_text())
    assert descriptor["name"] == "asi-bench"
    assert descriptor["status"] == "scaffold"
    assert descriptor["tasks"]["seed"] == 31415
    assert descriptor["tasks"]["official"] is False
    assert descriptor["conversion"]["status"] == "not-implemented"
    assert descriptor["verification"]["status"] == "not-implemented"
    assert descriptor["parity"]["status"] == "insufficient-evidence"

    parity = json.loads((ADAPTER / "parity_experiment.json").read_text())
    assert parity["status"] == "template"
    assert parity["scope"] == {
        "seed": 31415,
        "official": False,
        "asi_revision": None,
        "hf_revision": None,
    }
    assert parity["conversion_parity"]["tasks"] == []
    assert parity["agent_parity"]["results"] == []


def test_adapter_declares_only_supported_seed_and_levels() -> None:
    adapter = _load_adapter()
    assert adapter.SUPPORTED_SEED == 31415
    assert adapter.PROMPT_LEVELS == ("B1", "B2", "B3", "B4")
    # Revisions are now real pinned values (not placeholder strings)
    assert len(adapter.ASI_REVISION) == 40  # 40-char git SHA
    assert not adapter.ASI_REVISION.startswith("REPLACE_WITH_")

    valid = adapter.ASIBenchInstance(
        task_id="demo",
        instance_id="demo__seed31415",
        prompt_level="B1",
        seed=31415,
        instance_dir=ROOT,
        task_bundle_dir=ROOT,
    )
    adapter.validate_instance(valid)

    with pytest.raises(ValueError, match="only supports seed 31415"):
        adapter.validate_instance(valid.__class__(**{**valid.__dict__, "seed": 42}))

    with pytest.raises(ValueError, match="prompt_level"):
        adapter.validate_instance(
            valid.__class__(**{**valid.__dict__, "prompt_level": "B5"})
        )


def test_converter_rejects_seed42_and_bad_level(tmp_path: Path) -> None:
    adapter = _load_adapter()

    # seed42 is rejected by validate_instance before any I/O
    with pytest.raises(ValueError, match="only supports seed 31415"):
        adapter.validate_instance(
            adapter.ASIBenchInstance(
                task_id="demo",
                instance_id="demo__seed42",
                prompt_level="B1",
                seed=42,
                instance_dir=tmp_path,
                task_bundle_dir=tmp_path,
            )
        )

    # convert() rejects missing instance_dir
    instance = adapter.ASIBenchInstance(
        task_id="demo",
        instance_id="demo__seed31415",
        prompt_level="B1",
        seed=31415,
        instance_dir=tmp_path / "nonexistent_instance",
        task_bundle_dir=tmp_path / "nonexistent_bundle",
    )
    output_dir = tmp_path / "output"
    with pytest.raises((ValueError, FileNotFoundError)):
        adapter.convert(instance, output_dir)
    # No partial output should be left
    assert not output_dir.exists()


def test_convert_all_requires_task_ids_when_no_source_dir(tmp_path: Path) -> None:
    adapter = _load_adapter()
    # Without source_dir AND without task_ids → should raise
    with pytest.raises((ValueError, TypeError)):
        adapter.convert_all(None, tmp_path / "out")


def test_verifier_exits_nonzero_without_instance_json(tmp_path: Path) -> None:
    """Verifier must exit non-zero and not write reward.txt when metadata is missing."""
    script = ADAPTER / "verifier_template" / "score_entry.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert result.returncode != 0
    # No reward files should be created when infrastructure fails
    assert not list(tmp_path.rglob("reward.txt"))
    assert not list(tmp_path.rglob("reward.json"))


def test_parity_placeholder_reports_insufficient_evidence() -> None:
    result = subprocess.run(
        [sys.executable, str(ADAPTER / "parity_test.py"), "--mode", "full"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "insufficient-evidence"


def test_verifier_test_script_is_executable() -> None:
    assert os.access(ADAPTER / "verifier_template" / "test.sh", os.X_OK)


def test_converter_copies_complete_data_to_agent_and_verifier(tmp_path, monkeypatch) -> None:
    """Guards the seed31415 homotopy P3 missing-system.json regression (2026-10-09)."""
    adapter = _load_adapter()
    monkeypatch.setattr(adapter, "_render_task_md", lambda **_: "task")
    monkeypatch.setattr(adapter, "_build_dockerfile", lambda _: "FROM python:3.11\n")
    monkeypatch.setattr(adapter, "_materialize_evaluator_files", lambda *_: None)
    instance = tmp_path / "instance"
    (instance / "data" / "nested").mkdir(parents=True)
    (instance / "data" / "system.json").write_text('{"system": 1}')
    (instance / "data" / "nested" / "extra.json").write_text("extra")
    reference = instance / "reference"
    reference.mkdir()
    (reference / "answer.json").write_text("{}")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "task_eval.yaml").write_text("evaluation: {}\n")
    staging = tmp_path / "task"
    staging.mkdir()
    adapter._generate_task_dir(
        staging=staging, task_id="math.demo", instance_id="math.demo__seed31415",
        prompt_level="B1", task_meta={"input": {"files": [{"name": "system.json"}]}},
        task_eval={"evaluation": {}}, prompt_text="solve", instance_dir=instance,
        bundle_dir=bundle, reference_dir=reference,
        asi_revision="a" * 40, hf_revision="b" * 40,
    )
    for root in (staging / "environment" / "inputs", staging / "verifier" / "instance_data"):
        assert (root / "data" / "system.json").read_text() == '{"system": 1}'
        assert (root / "data" / "nested" / "extra.json").read_text() == "extra"
    metadata = json.loads((staging / "verifier" / "instance.json").read_text())
    assert metadata["requires_instance_data"] is True


def test_converter_rejects_missing_declared_data_root(tmp_path, monkeypatch) -> None:
    """Guards the seed31415 homotopy P3 missing-system.json regression (2026-10-09)."""
    adapter = _load_adapter()
    monkeypatch.setattr(adapter, "_render_task_md", lambda **_: "task")
    monkeypatch.setattr(adapter, "_build_dockerfile", lambda _: "FROM python:3.11\n")
    monkeypatch.setattr(adapter, "_materialize_evaluator_files", lambda *_: None)
    instance = tmp_path / "instance"
    instance.mkdir()
    reference = instance / "reference"
    reference.mkdir()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    staging = tmp_path / "task"
    staging.mkdir()
    with pytest.raises(ValueError, match="data"):
        adapter._generate_task_dir(
            staging=staging, task_id="math.demo", instance_id="math.demo__seed31415",
            prompt_level="B1", task_meta={"input": {"files": [{"name": "system.json"}]}},
            task_eval={"evaluation": {}}, prompt_text="solve", instance_dir=instance,
            bundle_dir=bundle, reference_dir=reference,
            asi_revision="a" * 40, hf_revision="b" * 40,
        )


def test_evaluator_materializer_rejects_unpinned_source_bytes(tmp_path, monkeypatch) -> None:
    """Guards the seed31415 P3 source revision mismatch (2026-10-09)."""
    adapter = _load_adapter()
    source = tmp_path / "asi"
    (source / "ai4sci_bench").mkdir(parents=True)
    (source / "ai4sci_bench" / "core.py").write_text("actual")
    monkeypatch.setenv("ASI_BENCH_SOURCE", str(source))
    spec = {
        "upstream": {"revision": adapter.ASI_REVISION},
        "files": [{"kind": "copy", "path": "ai4sci_bench/core.py",
                   "source": "ai4sci_bench/core.py",
                   "source_sha256": hashlib.sha256(b"expected").hexdigest()}],
    }
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        adapter._materialize_evaluator_files(spec, tmp_path / "evaluator")
