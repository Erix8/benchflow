# BenchFlow × ASI-Bench

This adapter converts public ASI-Bench seed31415 instances into native BenchFlow
tasks. Scores are local and non-official. Seed42, LLM/VLM judge tasks, tasks
requiring a submission sandbox, and tasks requiring network access are outside
the current conversion scope.

Each generated task contains an agent-visible `environment/inputs/data/` tree
and a separate verifier-owned `verifier/instance_data/data/` copy. BenchFlow
uploads `verifier/` only after the agent attempt. The verifier scores declared
prediction files against this immutable input and `verifier/reference/`.
Missing predictions are ordinary submission failures; missing or unsafe
verifier inputs produce `asi_error.json`, no reward, and a nonzero exit.

The verifier writes a scalar `reward.txt` and structured `reward.json` under
`/logs/verifier/` after a valid evaluation. A partial reward below 1 is a
BenchFlow `FAIL` classification, while the reward remains a valid ASI score.

`benchflow.py` converts instances; `main.py` is its CLI entry point. The
`evaluator_files.json` source revision must match `ASI_REVISION` in
`benchflow.py`. Converted tasks must be regenerated after changing the
converter or verifier template because they contain copied files.

The current `parity_experiment.json` remains a template. Do not claim scoring
parity until the same saved agent outputs have been scored by both this
verifier and `asibench score` and their details have been compared.
