# Setup and maintenance scripts

Put helpers for environment setup, fetching pinned upstream repositories,
dependency preparation, and maintenance here. Document prerequisites, arguments,
working-directory rules, and output paths for each helper.

Core configuration, execution, checking, and dataset logic belongs in the
`rtlprobe/` Python package as it is implemented. Keep credentials in local
environment/configuration outside version control.

This directory currently contains no executable helpers. The existing pipeline
scripts remain in [`../tooling/`](../tooling/README.md); the Dockerfile is at the
repository root. Build from the root, then use the launcher from `tooling/` as
documented in the tooling guide.
