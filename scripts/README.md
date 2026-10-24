# RTLProbe scripts

`rtlprobe.py` is the deterministic entry point used by the separate agent repository.
It takes explicit absolute `--data-root` and `--target-config` paths for target
operations and exposes qualification,
execution, and auditing. It has no prompt, response-import, or Hermes actions.
Agent-specific preparation/import/provenance use `rtlprobe-agents/scripts/planner.py`.
See [execution layout](../docs/execution-layout.md) for actions and data resolution.

`fetch-design.sh` obtains/checks pinned upstream sources using an explicit absolute
`RTLPROBE_DATA_ROOT` environment variable and one absolute manifest-path argument.
There is no default target or named-repository allowlist. Agents invoke this script from the main
checkout rather than maintaining another downloader.

Install Python dependencies from `requirements-dataset.lock.txt` in this repository's
own environment. Native Git, patch, Icarus, Verilator, and Yosys are required for
qualification and mutation execution. None of these scripts invokes a model API.
