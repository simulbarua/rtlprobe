# RTLProbe scripts

`rtlprobe.py` is the runner entry point for qualification, execution, and
auditing. Pass explicit absolute `--data-root` and `--target-config` paths for
target operations.
See [execution layout](../docs/execution-layout.md) for actions and data resolution.

`fetch-design.sh` obtains/checks pinned upstream sources using an explicit absolute
`RTLPROBE_DATA_ROOT` environment variable and one absolute manifest-path argument.
The selected manifest identifies the repository and its pinned revision.

Install Python dependencies from `requirements-dataset.lock.txt` in this repository's
own environment. Native Git, patch, Icarus, Verilator, and Yosys are required for
qualification and mutation execution.
