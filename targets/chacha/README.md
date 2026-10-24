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

The separate qualification control changes `chacha_qr.v:96` from addition to
subtraction. Dataset case `chacha-cf9ca6a8bc3bf5b4` uses the distinct site at line 99
and is `accepted_core` following explicit user approval on October 19, 2026.
See the [detailed case review and acceptance receipts](../../docs/reviews/chacha-cf9ca6a8bc3bf5b4.md);
the [trial report](../../docs/RTLProbe_ChaCha_Agent_Trial_2026-10-19.md) records setup and workflow limits.

Configure the separate agent checkout using `config/chacha.example.json` as a
template, with real absolute code/data/Python/manifest paths. From that checkout:

```sh
python3 -m rtlprobe_agents --config CONFIG_JSON fetch
python3 -m rtlprobe_agents --config CONFIG_JSON qualify
python3 -m rtlprobe_agents --config CONFIG_JSON prepare --max-candidates 1
```

Existing source checkouts must be clean and at the pinned commit. Import a saved
model response through the agent's `plan` action, then invoke `run` on its frozen
plan and `audit` on the published case. New qualification/planning on another host
is required before new generation; saved metadata auditing alone is not replay.

The current PyVerilog mapper rejects the ANSI function declaration in
`chacha_core.v`. A first constant-site proposal was rejected before execution.
The successful case uses the supported quarter-round file; do not bypass parsing
or edit the original sources to make an unsupported site pass.

This is a different repository/algorithm from SHA-256 but belongs to the same
Secworks crypto catalog lineage. Keep that relationship in final dataset splits.
