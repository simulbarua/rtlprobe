# ChaCha core target

Source: [secworks/chacha](https://github.com/secworks/chacha), commit
`7eaba360df9fed9fc2db98d5f3df81cf01e5b604`. Catalog: `Master Catalog!A14:V14`,
entry R013 in [the repository spreadsheet](../../docs/RTLProbe_Repository_Catalog.xlsx).

This target uses the unchanged `chacha_core.v`, `chacha_qr.v`, and existing
`tb_chacha_core.v`. The selected suite contains fifteen fixed 512-bit output
comparisons for 128/256-bit keys and 8/12/20 rounds. It is one simulation suite,
not fifteen independently executed tests or measured coverage. The 64-bit IV
configuration and first-block behavior are in scope. The wrapper, subsequent-block
counter progression, and diagnostic-only quarter-round printouts are not qualified
by this trial. Source LICENSE is retained; reported license is BSD-2-Clause.

`config.json` supplies the file list, pinned revision, resource limits, semantic
scope, and checker-control site. `checker.py` requires all ordered checkpoint
verdicts, the completion marker, and a consistent summary. Its expected words are
copied from the upstream testbench, which is not edited. The eighth vector's header
says TC2-2, but its task argument repeats TC2-1; unique checker IDs include invocation
order. Upstream prints completion before the summary; both are required.

Qualification uses the control defined in the manifest to prove that the
unchanged checker detects an intentional fault. Control-site validation does not
establish correctness of every possible mutation or measured test coverage.
Individual case labels, reviews and acceptance receipts live in the external
data root, not this target guide.

From the runner root, using its Python environment and an external data directory:

```sh
python scripts/rtlprobe.py --data-root /absolute/rtlprobe-data --target-config /absolute/rtlprobe/targets/chacha/config.json fetch
python scripts/rtlprobe.py --data-root /absolute/rtlprobe-data --target-config /absolute/rtlprobe/targets/chacha/config.json qualify
python scripts/rtlprobe.py --data-root /absolute/rtlprobe-data --target-config /absolute/rtlprobe/targets/chacha/config.json check
python scripts/rtlprobe.py --data-root /absolute/rtlprobe-data audit-data
```

Existing upstream checkouts must be clean and at the pinned revision. Fresh
qualification is required before generation on another host; saved-evidence
metadata auditing alone is not a replay. See [execution and data layout](../../docs/execution-layout.md)
for submitting machine proposals, execution and curation, and
[mutation operators](../../docs/mutation-operators.md) for the current pyslang
mapper and its constraints. Historical Pyverilog mutation-parser limitations do
not describe the current mapper; the experimental dependency graph still has
its own parser restrictions.

This is a different repository/algorithm from SHA-256 but belongs to the same
Secworks crypto catalog lineage. Keep that relationship in final dataset splits.
