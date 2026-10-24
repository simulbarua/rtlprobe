# ChaCha real-repository agent trial and mutation review

> `DATA_ROOT` and `EVIDENCE_ROOT` below name the data root and the sealed-evidence folder kept outside this repository; see [execution-layout.md](execution-layout.md) for where they live on a given machine.

Date: October 19, 2026, America/Los_Angeles. Status: **one validated case, human-approved and accepted_core**.

**Start the human review with the [expanded case dossier](reviews/chacha-cf9ca6a8bc3bf5b4.md).**
It explains what the single mutant is, distinguishes its three repeated executions,
shows source context and full first-failure outputs, and links the evidence for
each review question. The original sealed `REVIEW.md` is a short execution summary.

## Result for review

Case **`chacha-cf9ca6a8bc3bf5b4`** changes one addition to subtraction in the ChaCha
quarter-round. The original and restored design pass all fifteen existing output
comparisons. Each of three mutant executions consistently fails all fifteen,
with the predicted first failure. Lint, synthesis, source restoration, evidence
auditing, and duplicate protection pass. The project user explicitly approved this
case on October 19, 2026. The separate
[acceptance event](DATA_ROOT/data/reviews/chacha-cf9ca6a8bc3bf5b4.acceptance.json)
binds approval to the unchanged evidence manifest. Current dataset totals are
**12 accepted cases and 3 pending review**; sealed execution records retain their
historical pre-review state. Acceptance verification ran no fresh simulations.

```diff
--- a/src/rtl/chacha_qr.v
+++ b/src/rtl/chacha_qr.v
@@ -99 +99 @@
-      c0 = c + d1;
+      c0 = c - d1;
```

The changed arithmetic result feeds the following XOR/rotation and subsequent
rounds. This is a synthetic datapath defect. The operator is the existing approved
`unsigned32_root_add_to_sub` version 1.0; the operator registry and engine were not
changed. The distinct negative control uses line 96, `a0 = a + b;`.

## Catalog and upstream provenance

- [Repository catalog](RTLProbe_Repository_Catalog.xlsx): `Master Catalog!A14:V14`, R013, ChaCha stream cipher. Catalog bytes remain unchanged; SHA-256 is `f3d5fa16f706506aeae41d2d1e1ab295943d446240691223bcd47a9f0840208e`.
- Upstream: [secworks/chacha at the pinned commit](https://github.com/secworks/chacha/tree/7eaba360df9fed9fc2db98d5f3df81cf01e5b604).
- Commit: `7eaba360df9fed9fc2db98d5f3df81cf01e5b604`.
- Existing [core testbench](https://github.com/secworks/chacha/blob/7eaba360df9fed9fc2db98d5f3df81cf01e5b604/src/tb/tb_chacha_core.v), [quarter-round RTL](https://github.com/secworks/chacha/blob/7eaba360df9fed9fc2db98d5f3df81cf01e5b604/src/rtl/chacha_qr.v), and [upstream build manifest](https://github.com/secworks/chacha/blob/7eaba360df9fed9fc2db98d5f3df81cf01e5b604/chacha.core) were inspected at that commit. README, LICENSE, manifest, and Makefile are retained as qualification collateral.
- Main integration assets: [target manifest](../targets/chacha/config.json), [checker adapter](../targets/chacha/checker.py), and [scope/reproduction guide](../targets/chacha/README.md).

The catalog places this repository and SHA-256 in the same **Secworks crypto**
lineage. This trial establishes another real repository/algorithm within the
supported backend; it does not establish cross-lineage generalization. The new
proposal uses `split_group=secworks_crypto` and remains unassigned pilot development
data. Legacy per-repository group labels were not rewritten. Final split manifests
must reconcile the broader lineage before model exports.

## What the agent workflow actually did

The separate `rtlprobe-agents` checkout invoked main-repository scripts for pinned
fetch, qualification, hardware execution, and audits. It prepared a frozen input,
validated/imported the model response, derived exact AST-checked source edits, and
validated its sealed plan before calling main execution with the manifest hash.

The coding-model response was supplied by **Codex in this interactive session**,
with origin `interactive_assistant`. No autonomous model API backend or live Hermes
session ran. Provider/model/token/cost receipt fields remain unknown; zero controller
API calls does not imply a zero-cost interactive session. This is a real integration
test of the Python planning adapter, launcher, contracts, and runner, with manually
assisted repository setup and model response selection.

Main code, agents, and upstream source remain separate:

```text
github/rtlprobe/                       Shared execution and target integration
github/rtlprobe-agents/                Agent workflows and local config
rtlprobe-data/tools/dataset/vendor/chacha/  Pinned separate upstream checkout
rtlprobe-data/designs/chacha/           Current qualification dossier
rtlprobe-data/data/plans/               Frozen request/response/plan
rtlprobe-data/outputs/chacha/           Qualification and case evidence
```

The ignored local agent config is `config/chacha.local.json`; a portable path
template is in the agents repository at `config/chacha.example.json`. The existing
SHA-256 local config was left selected to its previous target.

## Observed validation

| Gate | Observed result |
|---|---|
| Pinned checkout | Clean, exact commit; fetch performed through the agent launcher |
| Existing TB | Original bytes retained; no replacement TB or expected-value edits |
| Qualification baseline | PASS, fifteen complete output comparisons |
| Separate checker control | Detected arithmetic fault at a different source site |
| Case original | PASS, fifteen comparisons |
| Mutant executions 1, 2, 3 | All functional FAIL; each fails fifteen comparisons with identical signatures |
| Predicted first checkpoint | Confirmed: `case01_tc1_1` |
| Restored execution | PASS, fifteen comparisons |
| Restoration identity | Exact original source tree restored by reverse patch |
| Mutant identity | Same source hashes and executable across all three runs |
| Patch scope | Exactly one RTL file and one operator token; checker unchanged |
| Lint/Yosys | Original and mutant passed required commands; warnings retained |
| Saved-evidence audit | PASS using the frozen checker, with zero fresh simulations |
| Repeated plan invocation | One duplicate reused, zero new executions; only one ChaCha case exists |
| Software suites | 55 core tests and 32 agent tests passed |
| Previous records | All 2,354 captured active files and 1,987 original workarea files unchanged |
| Dataset totals at execution | 15 cases: 11 accepted, 4 pending review; only this one case added. After human approval: 12 accepted, 3 pending. |
| Existing SHA-256 qualification check | Still passes |

The selected upstream suite is one simulation with fifteen comparison checkpoints;
these are not fifteen independent test executions. It includes 128/256-bit keys
and 8/12/20 rounds with zero, patterned, one-bit, and fixed random-looking vectors.
It tests the configured 64-bit-IV core's first-block behavior. No measured source
coverage, independent per-test coverage, qualified netlist source mapping, full
protocol verification, or counter-progression coverage is claimed. The unmodified
diagnostic quarter-round task prints values but has no independent pass/fail oracle.

Successful qualification logged **1.377 seconds** of hardware-command wall time
and **1.314 CPU seconds**. The case logged **1.532 seconds** of hardware-command
wall time and **1.408 CPU seconds**. These are sums of recorded subprocess costs,
not end-to-end campaign time. They exclude downloads, failed setup, parsing/planning,
software suites, interactive model usage, documentation, and human review.

## Setup failures and manual intervention

1. AES (R009) was initially inspected but deferred before qualification. Its
   candidate sites were a poor match for the current narrow mutation operators;
   its existing benches also emit waveform files. No AES mutation or replacement
   verification environment was created.
2. ChaCha's first adapter assumed summary-before-completion ordering. The actual
   baseline log prints completion before the summary. Qualification correctly
   rejected that log as infrastructure error. The adapter was corrected and tested,
   then a new qualification succeeded; the original attempt remains retained.
3. The first model response proposed a key-mode-specific SIGMA1 constant fault.
   The response passed the JSON contract but AST mapping failed on PyVerilog's
   unsupported ANSI function declaration in `chacha_core.v` (line 94). No mutation
   was executed or published for that response. The raw error currently propagates
   as a traceback; friendlier unsupported-site reporting is still needed.
4. Codex manually selected one bounded fallback response at `chacha_qr.v:99`, using
   the existing arithmetic operator in the already mappable module. This was not
   an automatic response-repair loop. The rejected response and error remain saved.
   Only one dataset mutation was executed, and it succeeded.

The new checker mapping is a manual hardware-integration asset. It preserves all
fifteen expected words from the unchanged upstream TB and requires complete ordered
verdicts, matching failure details, completion, consistent summary, and clean
simulator status. One upstream header says TC2-2 while its task argument repeats
TC2-1; ordinal-prefixed IDs distinguish both comparisons. The adapter/checkpoint
mapping was not generated by an autonomous qualification agent.

## Evidence locations

All paths below are relative to the explicitly configured data root:

| Record | Path |
|---|---|
| Qualification dossier | `designs/chacha/design.json`, `designs/chacha/REPO.md` |
| Successful qualification | `outputs/chacha/qualification/5197fcd16058-20261020T020211206229Z/` |
| Rejected first qualification | `outputs/chacha/qualification/cc524ec031ce-20261020T020144194492Z/` |
| Frozen input | `data/plans/planner-cc74275372d78a33/input/` |
| Rejected first response | `data/plans/planner-cc74275372d78a33/response.json` |
| Successful response | `data/plans/planner-cc74275372d78a33/response-qr.json` |
| Frozen plan and planning receipt | `data/plans/planner-cc74275372d78a33/plan-345bb15b8b838c33/` |
| Case review, patch, logs, snapshots, manifests | `outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/` |
| Current case index | `data/manifests/chacha-cf9ca6a8bc3bf5b4.json` |
| Batch report and immutable invocation records | `outputs/chacha/batches/batch-d3377b202c6e7ed8/` |

The parent project workspace's `chacha-agent-verification/` contains catalog
selection, upstream test mapping, qualification/planning failure logs, first-run and
duplicate reports, test outputs, integrity receipts, and a verification manifest.
The earlier AES inspection is retained in `aes-agent-verification/`.

## What still requires manual work

- **New repository admission:** choose a catalog entry, audit its source/build/TB,
  define a compatible target manifest and semantic scope, and author/test the
  trusted checker adapter. Automated catalog ingestion/discovery and general
  qualification-agent reasoning are not implemented.
- **Planning:** provide a coding-model response to the frozen request. This trial
  used interactive Codex. Hermes can orchestrate the existing skill externally,
  but a live Hermes session/model configuration was not validated here.
- **Unsupported source syntax:** currently requires source/site selection or
  deliberate parser/backend development. This trial did not relax the AST checks
  or edit upstream source to bypass the limitation.
- **Acceptance:** human review remains required for future cases. This case's
  explicit approval has been recorded; automated validation alone does not create
  `accepted_core` status.
- **BaruaLabs:** transfer/clone code and data when authorized, rebuild dependencies,
  configure the four explicit paths, and qualify that host before new generation.

Decision: retain the single successful case as `accepted_core` following explicit
user approval, preserving sealed evidence and all previous approvals. Open work: autonomous target admission,
parser capability screening/error reporting, live Hermes validation, and final
lineage-aware exports. This case's review is complete. Next actions for the project
remain subject to the existing implementation and migration plan; no additional
batch, push, commit, model backend, or host migration was performed.
