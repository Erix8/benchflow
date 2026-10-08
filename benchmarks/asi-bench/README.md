# BenchFlow × ASI-Bench

This directory contains the integration scaffold for converting public
[ASI-Bench](https://github.com/apexin-ai/ASI-Bench) instances into native
BenchFlow tasks. The converter and verifier are intentionally not implemented
in this change; every execution path fails closed rather than producing an
empty task set or a misleading zero reward.

## Scope

The planned adapter accepts only already-materialized `seed31415` instances.
Those instances carry public references for reproducible local scoring, so all
reported results are **local and non-official**. `seed42` remains an ASI-Bench
submission workflow and is not accepted here.

The first implementation will also skip tasks whose evaluation requires an
LLM/VLM judge, tasks that require `runner.submission_sandbox`, and networked
tasks until their egress policy is reviewed. Every skipped task must be listed
with a reason; silent omission is not acceptable.

Neither source tasks nor references are committed to BenchFlow. A future
converter will materialize them from immutable ASI-Bench Git and Hugging Face
dataset revisions, validate both revisions, and create one BenchFlow task per
ASI task, prompt level, and instance.

## Planned task boundary

The agent will see the selected B1–B4 prompt and public instance inputs under
`environment/`. Reference material and evaluator code belong under
`verifier/`, which BenchFlow uploads only after the agent attempt. The verifier
will run inside the task sandbox and write both `reward.txt` and a richer
`reward.json` only after valid evaluation.

Missing prediction artifacts are ordinary submission failures and may score
zero. Evaluator setup/runtime failures are different: they must exit nonzero
without writing a reward so BenchFlow records verifier infrastructure failure.

## Files

- `benchflow.py` defines the pinned-source and seed31415 converter contracts.
- `main.py` delegates to the converter CLI.
- `verifier_template/` defines the future in-sandbox verifier entry point; it
  currently raises an explicit integration error.
- `parity_test.py` reserves structural, evaluator, and side-by-side parity
  entry points; all currently report insufficient evidence and exit nonzero.
- `parity_experiment.json` remains in `template` state until real experiments
  compare ASI-Bench and BenchFlow scoring on identical outputs.
- `run_asi_bench.py` and `asi-bench.yaml` reserve the execution surface.
- `benchmark.yaml` describes the planned adapter without claiming completion.

## Current status

This scaffold is not runnable. In particular, it does not download data,
generate tasks, install ASI-Bench evaluator files, run scoring, summarize jobs,
or establish parity. These capabilities will be implemented incrementally
after immutable source revisions and evaluator file hashes are selected.

The expected parity gate result is therefore `insufficient-evidence`, never
`parity-confirmed`.
