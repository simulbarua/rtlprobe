# RTLProbe operator implementation report — October 24, 2026

Runner-only, uncommitted changes. The accepted_auto session had finished and its
implementation was present at runner commit 7584c56 before this work began.
A separate backend session was active; its changes are excluded from this report's
diffstat. No project records, launcher, Hermes skill, accepted case or live data
file was edited by this session. No case was generated and no simulation was run.

## 1. Diffstat

Session changes relative to the starting checkout (shared README/batch hunks
attributed separately from the backend work):

| File | Added | Removed |
|---|---:|---:|
| `README.md` | 48 | 1 |
| `experiments/localization/baseline.py` | 19 | 1 |
| `requirements-dataset.in` | 1 | 0 |
| `requirements-dataset.lock.txt` | 2 | 0 |
| `rtlprobe/batch.py` | 7 | 1 |
| `rtlprobe/mutation.py` | 294 | 111 |
| `rtlprobe/operators.json` | 71 | 1 |
| `rtlprobe/schemas/proposal_v2.json` | 5 | 3 |
| `rtlprobe/sv_frontend.py` | 107 | 0 |
| `rtlprobe/candidates.py` | 120 | 0 |
| `scripts/operator_regression.py` | 51 | 0 |
| `scripts/operator_sites.py` | 49 | 0 |
| `tests/test_operators.py` | 230 | 0 |
| `tests/fixtures/operators/OpenTitan-LICENSE` | 202 | 0 |
| `tests/fixtures/operators/README.md` | 6 | 0 |
| `tests/fixtures/operators/timer_core.sv` | 48 | 0 |
| `docs/operator-sites-2026-10-24.json` | 6032 | 0 |
| Subtotal, excluding this report | 7292 | 118 |

This report is one additional new file. The 6,032-line JSON inventory lists every
reachable site with exact bytes, hashes, per-file counts and explicit rejections.

## 1a. Accepted-case regression gate

```sh
PYTHONDONTWRITEBYTECODE=1 .venv-operators/bin/python scripts/operator_regression.py --data-root /Users/simulbarua/Work/ml_projects/RTLProbe/local/rtlprobe-data
```

Result: **15 accepted cases, 15 byte-identical patches, 0 mismatches**;
14 SHA-256 and 1 ChaCha, all `accepted_core`, 0 `accepted_auto`.
Receipts/manifests were verified, source was read from each sealed `rtl/original`,
and the recorded operator/site was applied in memory. The re-derived unified
patch bytes matched each sealed `mutation.patch`. There are no mismatch diffs.
The gate prints JSON, writes nothing, and runs no simulations.

Both approved operators now use pyslang. Their IDs and versions remain unchanged.
Legacy mapper strings are accepted as historical provenance only after every
other target field matches the pyslang derivation. Pyverilog remains installed
because the pilot dependency graph still imports it; mutation does not use it.
Pinned parser: [pyslang 12.0.0](https://pypi.org/project/pyslang/12.0.0/), with its
`nanobind-backend==1.0.0` dependency also pinned.

## 2. Three registry entries, verbatim

```json
[
  {
    "id": "relational_operator_replace",
    "version": "1.0",
    "status": "proposed",
    "approval_scope": "Implementation proposal only; user confirmation and candidate-rule adoption required before case use.",
    "review": "Fixture validation only; no user operator approval or case acceptance.",
    "implementation": "rtlprobe/mutation.py:locate_operator, apply",
    "fixture_tests": "tests/test_operators.py",
    "family": "comparison_boundary",
    "preconditions": [
      "One AST-located binary comparison on one line; exactly one comparison at the site.",
      "Operands are identifiers, selects or literals with known integral widths.",
      "Exact source hash, path and token span match."
    ],
    "edit": "Swap one token: >= with >, <= with <, or == with !=. Reference: OpenTitan timer_core.sv:39 >= to >.",
    "exclusions": [
      "=== and !==",
      "Unknown-width operands, including signed operands of unknown width",
      "Macro-derived, multiline, string or comment sites; generate conditions",
      "Generated *_reg_top.sv and *_reg_pkg.sv files",
      "Ambiguous sites; no-op edits"
    ]
  },
  {
    "id": "condition_invert",
    "version": "1.0",
    "status": "proposed",
    "approval_scope": "Implementation proposal only; user confirmation and candidate-rule adoption required before case use.",
    "review": "Fixture validation only; no user operator approval or case acceptance.",
    "implementation": "rtlprobe/mutation.py:locate_operator, apply",
    "fixture_tests": "tests/test_operators.py",
    "family": "control",
    "preconditions": [
      "One AST-located if condition or ternary selector, a single expression on one line.",
      "Exact source hash, path, reset identifier policy and token span match.",
      "Dependency: the separately adopted candidate rule must include if and ternary conditions before any case uses this operator.",
      "One edit per case; source hash prevents stacking edits."
    ],
    "edit": "Wrap the condition in !(...) or remove its existing outer ! token, preserving other bytes. Reference: if (enable) becomes if (!(enable)).",
    "exclusions": [
      "rst_ni, rst_n, reset_n (existing crypto reset), and manifest reset_identifiers",
      "Conditions already mutated in the case (source-hash mismatch)",
      "Macro-derived, multiline or generate sites; pattern conditions",
      "Generated *_reg_top.sv and *_reg_pkg.sv files",
      "Ambiguous sites"
    ]
  },
  {
    "id": "logic_operator_swap",
    "version": "1.0",
    "status": "proposed",
    "approval_scope": "Implementation proposal only; user confirmation and candidate-rule adoption required before case use.",
    "review": "Fixture validation only; no user operator approval or case acceptance.",
    "implementation": "rtlprobe/mutation.py:locate_operator, apply",
    "fixture_tests": "tests/test_operators.py",
    "family": "logic",
    "preconditions": [
      "Exactly one AST-located binary bitwise/logical operator at the site on one line.",
      "Both operand widths are known integral widths.",
      "Exact source hash, path and token span match."
    ],
    "edit": "Swap one token: & with |, or && with ||. Reference: assign y = a & b becomes assign y = a | b.",
    "exclusions": [
      "Unary reduction operators",
      "Macro-derived, multiline, string or comment sites; generate constructs",
      "Assert or cover properties",
      "Generated *_reg_top.sv and *_reg_pkg.sv files",
      "Ambiguous sites; no-op edits"
    ]
  }
]
```

## 3. Test commands and results

From the runner checkout:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv-operators/bin/python -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 .venv-operators/bin/python -m unittest discover -s experiments/localization -q
```

```text
Ran 103 tests in 2.581s
OK
Ran 8 tests in 3.405s
OK
```

The runner suite includes 21 new operator tests and the backend tests present in
the shared working tree. Tests use in-memory sources and temporary roots, no
simulations. Covered: all replacement pairs, control negation/removal, exact
hash/span rejection, byte-preserving apply/revert, repeat-apply rejection,
representation/case/CRLF preservation, excluded syntax, macros, generated paths,
reset policy, candidate-coordinate coverage, proposed approval gate, and a
read-only temporary regression gate including a deliberate mismatch diff.
The pinned OpenTitan `timer_core.sv` fixture locates line 39 and a conditional.
The original source SHA-256 is
`9ebebe1c5517edbba276c25e7594a43ae11588a5627c0e070fe6b927c6944644`.
`git diff --check` passed.

## 4. Reachable-site counts and mapping coverage

Counts are operator/site combinations, not generated mutants or guaranteed
checker detections. They use the qualified crypto sealed originals and the
unmodified OpenTitan checkout at `3a7f6947247254fcc2fd05143c18a2646f75c7ee`.
OpenTitan targets are candidate targets pending gate 1, not qualified targets.
Widths are resolved per standalone file using default parameter values.

A = unsigned32_root_add_to_sub; K = literal_lsb_flip32;
R = relational_operator_replace; C = condition_invert; L = logic_operator_swap.

| Target / available scope | A | K | R | C | L | Status |
|---|---:|---:|---:|---:|---:|---|
| sha256 | 13 | 84 | 4 | 21 | 1 | complete |
| chacha | 4 | 10 | 7 | 24 | 0 | complete |
| opentitan_crc32 | 0 | 0 | 0 | 2 | 1 | complete |
| opentitan_rv_timer | 0 | 0 | 3 | 2 | 1 | partial |
| opentitan_uart | 0 | 0 | 4 | 13 | 6 | partial |

All **200/200 enumerated operator/site combinations** map to exact candidate
file/line/column/start/end coordinates (100% for each nonempty operator/target
cell; zero-site denominators are N/A). This is syntax mapping coverage, not
statement localization recall, dependency graph coverage, or complete coverage
of files that failed parsing. The source-only successor is independent of the
operator registry and case labels.

Per-file counts:

| File | A | K | R | C | L |
|---|---:|---:|---:|---:|---:|
| `src/rtl/sha256_core.v` | 12 | 20 | 1 | 17 | 0 |
| `src/rtl/sha256_w_mem.v` | 1 | 0 | 3 | 4 | 1 |
| `src/rtl/sha256_k_constants.v` | 0 | 64 | 0 | 0 | 0 |
| `src/rtl/chacha_core.v` | 0 | 10 | 7 | 24 | 0 |
| `src/rtl/chacha_qr.v` | 4 | 0 | 0 | 0 | 0 |
| `hw/ip/prim/rtl/prim_crc32.sv` | 0 | 0 | 0 | 2 | 1 |
| `hw/ip/rv_timer/rtl/timer_core.sv` | 0 | 0 | 3 | 2 | 1 |
| `hw/ip/uart/rtl/uart_rx.sv` | 0 | 0 | 2 | 6 | 5 |
| `hw/ip/uart/rtl/uart_tx.sv` | 0 | 0 | 2 | 7 | 1 |

Unavailable files (counts **unknown**, not zero):

- `hw/ip/rv_timer/rtl/rv_timer.sv`
- `hw/ip/uart/rtl/uart.sv`
- `hw/ip/uart/rtl/uart_core.sv`

All three report `CouldNotOpenIncludeFile` plus `UnknownDirective`: the
standalone-byte API has no manifest include/package/macro context. No source
was rewritten, macro stubbed, or unsupported file counted as zero. The JSON
inventory preserves the diagnostics and source-root paths. The other listed
OpenTitan files parsed successfully. In `timer_core.sv`, relational sites are
lines 32, 39, 45; condition sites 30, 32; logic site 39. Relational expressions in
generate bodies are admitted, while generate conditions are excluded; control
and logic operators exclude generate constructs entirely.

The proposed CRC table control has no site under either existing approved
operator. Its 256 literals assign to the function return `crc32_byte_calc`,
which is not a declared unsigned register or localparam. That exclusion is
preserved; no substitute control or extra operator was implemented.

## 5. Deviations and limits

- Complete OpenTitan counts could not be obtained for the three files above.
  Add real, hash-bound parser context before relying on full-target counts.
- The source candidate successor inventories functions, generate constructs,
  parameter overrides and instance arrays. The pilot **dependency graph** still
  rejects these classes and retains pyverilog. Its failures are not hidden by a
  fallback graph; this work does not make full OpenTitan C1/C4 extraction ready.
- The candidate code now includes if/ternary sites, but the separate candidate
  rule order has not adopted or frozen this rule. The registry records that
  prerequisite and all three new entries remain proposed.
- `reset_n` is excluded alongside `rst_n`, `rst_ni` and manifest reset names,
  because it is the actual asynchronous reset in both existing crypto targets.
  Manifest custom names use `reset_identifiers`; preflight binds that policy and
  the repository-relative target path before applying an edit.
- Proposal-v2 schema changes admit the three families and an empty replacement
  for deletion of `!`; apply still verifies the exact supported edit. No planner
  or agents launcher changes were made.
- No new control mutant, simulation, qualification, acceptance, or commit was
  performed. The backend session's work is separate.

## 6. Follow-ups not done

1. User confirmation of the three proposed registry entries after reviewing the
   tests, limits and candidate support. No approval is inferred from fixture success.
2. Adopt `if`/ternary inclusion in the separate candidate-rule order; extend the
   dependency extractor for rejected classes before using those graph conditions.
3. Supply reproducible, hash-bound include/package/define context for the three
   unavailable OpenTitan files, then rerun the complete inventory. Resolve the
   unreachable CRC table control with the user; no operator expansion is implicit.
4. Update the agent planner/launcher separately to propose the new site shape,
   propagate manifest resets, and consume the new registry once approved.
5. Complete OpenTitan control/restoration gates and spec-store prerequisites in
   their own work orders after the relevant operators are approved.
6. Append the project change-log row below after review. This session did not
   edit `project/`. Commit remains the user's action.

Suggested change-log row (not appended):

| 2026-10-24 | implementation verified, partial OpenTitan inventory | Runner mutation mapping migrated to pyslang 12.0.0; both approved operator IDs/versions preserved; all 15 accepted patches re-derived byte-identically; three new operators remain proposed; source candidate extraction includes if/ternary sites with 200/200 enumerated sites mapped; 103 runner and 8 localization tests pass without simulations; three OpenTitan files need include/package context, CRC function-return literals remain outside the approved domain, and the pilot dependency graph retains pyverilog | Codex, at user request | Implement amendment 5b and the operators work order without changing accepted evidence | runner working tree; rtlprobe/docs/RTLProbe_Operators_Report_2026-10-24.md; rtlprobe/docs/operator-sites-2026-10-24.json; no commit |
