# RTLProbe implementation

Put the project's Python implementation directly in this directory, without a
`src/` parent. The outer repository and this Python package have different roles.

Responsibilities include configuration validation, pipeline execution, compilation
and simulation, checker adapters, lint and synthesis, artifact extraction, approved
mutation operators, evidence auditing, dataset processing, localization models,
and evaluation.

This directory is currently a scaffold. Add modules and Python package metadata
as functionality is implemented. Existing executable tooling remains under
[`../tooling/`](../tooling/README.md).

Keep target-specific source lists in `targets/`, downloaded upstream code in
`vendor/`, and generated artifacts in `outputs/`. Agent implementations, prompts,
and model-provider integrations belong in the separate agents repository.
