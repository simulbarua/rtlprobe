# Human review: chacha-cf9ca6a8bc3bf5b4

> `DATA_ROOT` and `EVIDENCE_ROOT` below name the data root and the sealed-evidence folder kept outside this repository; see [execution-layout.md](../execution-layout.md) for where they live on a given machine.

**Status: accepted_core. There is one bug variant, tested three times. The project user explicitly approved this case on October 19, 2026 (America/Los_Angeles).**

Approval: “I reviewed case chacha-cf9ca6a8bc3bf5b4 and approve it. Record my approval and mark it as accepted.”
The [human review receipt](DATA_ROOT/data/reviews/chacha-cf9ca6a8bc3bf5b4.json)
and [acceptance event](DATA_ROOT/data/reviews/chacha-cf9ca6a8bc3bf5b4.acceptance.json)
bind that decision to the unchanged case manifest. The reviewed version of this
document was archived before this status update in
[the approval verification directory](EVIDENCE_ROOT/verification-2026-10/chacha-acceptance-verification/before-review-dossier.md).

This document records the completed human review. It expands the short, sealed `REVIEW.md`
without changing that execution artifact, its hashes, the original simulations,
or their historical pre-review state. Current acceptance is recorded separately.
The review is bound to case manifest
`0995cd3506bfdfd949daa1796871acd15fd2f1dd14ef071f79ab550ed7671bb1`.

## 1. What is a mutant, and how many are here?

A **mutant** is a modified copy of a correct reference design containing an
intentional synthetic defect. It is the buggy RTL you are deciding whether to
include in the dataset. It is not a testbench or a model.

For this case, the runner created three source snapshots:

| Snapshot | Meaning | Open the actual source |
|---|---|---|
| Original | Unchanged, pinned upstream RTL | [original chacha_qr.v, line 99](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/rtl/original/src/rtl/chacha_qr.v:99>) |
| Buggy / mutant | One source token changed from `+` to `-` | [mutant chacha_qr.v, line 99](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/rtl/buggy/src/rtl/chacha_qr.v:99>) |
| Restored | Buggy source reverse-patched back to the exact original bytes | [restored chacha_qr.v, line 99](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/rtl/restored/src/rtl/chacha_qr.v:99>) |

The old summary's **“mutant 1”, “mutant 2”, and “mutant 3” are execution runs 1–3
of the same buggy source and same compiled mutant executable**. They are not three
different bugs. The case validation contains five functional executions: one
original run, three mutant runs, and one restored run. Qualification's original
and separate checker-control executions are additional setup evidence.

## 2. Start the review with this exact edit

| Original behavior | Mutated behavior |
|---|---|
| `c0 = c + d1;` | `c0 = c - d1;` |
| Add the rotated intermediate word to `c` | Subtract that word from `c` |

Module: `chacha_qr`. File: `src/rtl/chacha_qr.v`. Line: **99**, column **14**.
Bug family: `datapath_arithmetic`. Operator: `unsigned32_root_add_to_sub`, version
1.0. Exactly one byte differs at zero-based file offset 3383 (`+` → `-`).

[Open the complete patch](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/mutation.patch>).

The surrounding original RTL, read directly from the preserved source snapshot:

```text
 96        a0 = a + b;
 97        d0 = d ^ a0;
 98        d1 = {d0[15 : 0], d0[31 : 16]};
 99        c0 = c + d1;
100        b0 = b ^ c0;
101        b1 = {b0[19 : 0], b0[31 : 20]};
102        a1 = a0 + b1;
103        d2 = d1 ^ a1;
104        d3 = {d2[23 : 0], d2[31 : 24]};
105        c1 = c0 + d3;
106        b2 = b1 ^ c1;
107        b3 = {b2[24 : 0], b2[31 : 25]};
108  
109        internal_a_prim = a1;
110        internal_b_prim = b3;
111        internal_c_prim = c1;
112        internal_d_prim = d3;
```

Only the addition on line 99 changes. Variable widths, XORs, rotations, remaining
additions, control logic, testbench, and expected outputs retain their original
source bytes. The original and restored seven-file snapshot trees match exactly;
only `chacha_qr.v` differs in the buggy tree.

## 3. Why is this a functional bug?

`a`, `b`, `c`, `d`, and the intermediate words are unsigned 32-bit values.
Line 98 rotates an XOR result left by 16 bits into `d1`. The intended next step
adds `d1` to `c`, modulo 2^32. The mutant subtracts it instead.

For a small **illustrative example**, `c=5` and `d1=3` would produce `c0=8` in the
original and `c0=2` in the mutant. These numbers explain the edit; they are **not
captured signal values from the recorded simulation**. Some operands can mask
this defect, so detection must be demonstrated using the existing tests.

The subsequent XOR uses `c0`, then rotates the result and feeds later additions
and XORs. The core feeds quarter-round outputs back into its state during further
rounds. This explains how the changed operation can affect the final 512-bit
block. This dependency explanation is inferred from the preserved RTL; no
cycle-accurate internal first-divergence trace was measured.

The core instantiates the `chacha_qr` module four times (`qr0`–`qr3`). One source
edit therefore affects all four instances of that module. The dataset label is
one edited source statement, not one uniquely identified physical adder.
See [core instantiations](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/rtl/original/src/rtl/chacha_core.v:194>) and
[state feedback](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/rtl/original/src/rtl/chacha_core.v:408>).

A primary algorithm reference also supports this specific arithmetic requirement:
the ChaCha quarter-round uses addition modulo 2^32 at this step.
[RFC 8439 §2.1](https://www.rfc-editor.org/rfc/rfc8439.html#section-2.1).
This reference supports the quarter-round operation only. The tested upstream core
also supports original 128-bit-key, 64-bit-IV and 8/12-round variants; this case is
not a claim of full RFC 8439 conformance. The frozen proposal's requirement remains
classified `inferred_from_rtl_and_checker`; this review does not rewrite that record.

**Your judgment:** is replacing this required addition with subtraction a useful,
plausible synthetic arithmetic defect for our dataset? It is a simple, strongly
exposed bug; it is not presented as a historical developer bug or a difficult,
rarely activated protocol defect.

## 4. How does the existing testbench detect it?

The unmodified upstream `tb_chacha_core.v` supplies fixed keys, IVs, round counts,
and expected 512-bit outputs. It waits for output-valid and compares the actual
full block to its expected block. A discrepancy prints a failure plus both words.
Open [the actual checker](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/rtl/original/src/tb/tb_chacha_core.v:419>).

The suite has **15 comparisons in one simulation**, including 128/256-bit keys
and 8/12/20 rounds. These are checkpoints, not fifteen independent test invocations
or measured source coverage. The eighth vector repeats a printed task label
`TC 2-1`; the ordinal-prefixed IDs distinguish it from the seventh vector.
Diagnostic-only quarter-round printouts are not counted as assertions.

The first checkpoint uses zero key and IV, a 128-bit key, and eight rounds. Zero
external key/IV does not imply an all-zero internal state: the design initializes
constant words as well. The observed first mutant failure is the predicted
`case01_tc1_1`.

**Expected full 512-bit output**, grouped into 32-bit words for reading:

```text
e28a5fa4 a67f8c5d efed3e6f b7303486
aa8427d3 1419a729 572d7779 53491120
b64ab8e7 2b8deb85 cd6aea7c b6089a10
1824beeb 08814a42 8aab1fa2 c816081b
```

**Observed mutant output**, identical across the three mutant runs:

```text
5684be87 43cf1ec5 7c1f1c59 e2d50220
9558a5c7 3008998a 0279a9e9 09e17566
c3f0bd87 14406eb1 0348f2cc 7401b79f
7e4b5936 f3f19938 667fbdb9 31fe4fbe
```

These full blocks differ in **249 of 512 bits**,
computed directly by XORing the two recorded words. The recorded failure excerpt is:

```text
*** ERROR: TC 1-1 not successful
Expected: 0xe28a5fa4a67f8c5defed3e6fb7303486aa8427d31419a729572d777953491120b64ab8e72b8deb85cd6aea7cb6089a101824beeb08814a428aab1fa2c816081b
Got:      0x5684be8743cf1ec57c1f1c59e2d502209558a5c73008998a0279a9e909e17566c3f0bd8714406eb10348f2cc7401b79f7e4b5936f3f19938667fbdb931fe4fbe
```

[Jump to this failure in the raw first-mutant log](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/commands/mutant_1/stdout.log:447>).
There is no need to hand-compare every hex digit; the preserved full-block checker
and its logs show what was compared. The expected word was not edited.

## 5. What actually happened on every comparison?

The table below is extracted from the original, all three mutant, and restored
JSON outcome records, rather than copied from the model's prediction. “Different
bits” compares expected versus mutant output; the same discrepancy is present in
all three mutant runs.

| Checkpoint | Key bits | Rounds | Original | Same mutant, runs 1 / 2 / 3 | Restored | Different bits / 512 |
|---|---:|---:|---|---|---|---:|
| case01_tc1_1 | 128 | 8 | PASS | FAIL / FAIL / FAIL | PASS | 249 |
| case02_tc1_2 | 128 | 12 | PASS | FAIL / FAIL / FAIL | PASS | 264 |
| case03_tc1_3 | 128 | 20 | PASS | FAIL / FAIL / FAIL | PASS | 246 |
| case04_tc1_4 | 256 | 8 | PASS | FAIL / FAIL / FAIL | PASS | 263 |
| case05_tc1_5 | 256 | 12 | PASS | FAIL / FAIL / FAIL | PASS | 264 |
| case06_tc1_6 | 256 | 20 | PASS | FAIL / FAIL / FAIL | PASS | 245 |
| case07_tc2_1 | 128 | 8 | PASS | FAIL / FAIL / FAIL | PASS | 256 |
| case08_tc2_1 | 256 | 8 | PASS | FAIL / FAIL / FAIL | PASS | 261 |
| case09_tc3_1 | 128 | 8 | PASS | FAIL / FAIL / FAIL | PASS | 256 |
| case10_tc4_1 | 128 | 8 | PASS | FAIL / FAIL / FAIL | PASS | 260 |
| case11_tc5_1 | 128 | 8 | PASS | FAIL / FAIL / FAIL | PASS | 235 |
| case12_tc6_1 | 128 | 8 | PASS | FAIL / FAIL / FAIL | PASS | 232 |
| case13_tc7_1 | 128 | 8 | PASS | FAIL / FAIL / FAIL | PASS | 255 |
| case14_tc7_2 | 256 | 8 | PASS | FAIL / FAIL / FAIL | PASS | 258 |
| case15_tc8_1 | 128 | 8 | PASS | FAIL / FAIL / FAIL | PASS | 257 |

The model predicted a functional mismatch at the first checkpoint; that prediction
was confirmed. It did not predict the exact incorrect output words or claim to
have measured the number of failures before execution. All fifteen failures were
subsequently observed.

## 6. Review the execution and restoration evidence

| Execution | Simulator exit | Passing comparisons | Failing comparisons | Functional result | Evidence |
|---|---:|---:|---:|---|---|
| Original source | 0 | 15 | 0 | pass | [raw log](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/commands/original/stdout.log>) |
| Same mutant, run 1 | 0 | 0 | 15 | functional_fail | [raw log](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/commands/mutant_1/stdout.log>) |
| Same mutant, run 2 | 0 | 0 | 15 | functional_fail | [raw log](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/commands/mutant_2/stdout.log>) |
| Same mutant, run 3 | 0 | 0 | 15 | functional_fail | [raw log](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/commands/mutant_3/stdout.log>) |
| Reverse-patched source | 0 | 15 | 0 | pass | [raw log](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/commands/restored/stdout.log>) |

All five processes completed without timeout. The mutant process exit code is
zero because this upstream testbench reports mismatches in its log; zero process
exit does not mean correct RTL. The checker adapter identifies the completed
functional failures from the actual verdicts and expected/actual words.

Restoration is a useful causal check: reversing this single edit restores both
original source identity and passing behavior under the same testbench. That
supports attributing the observed failure to this mutation. It does not establish
correctness for all possible inputs or a formal equivalence result.

The three mutant executions use executable SHA-256
`8ea44a407fbb69d0cfb6dba863e7382e4b30c06010f67b15b0f71fa2562387b1`. The source hashes and failure signatures
match across all three; their stdout logs are also byte-identical. The separately
compiled original/restored binaries need not have the same hash, because their
embedded build paths can differ; exact restored **source** identity is checked.

| Structural check | Process result | Command / metadata | Logs |
|---|---|---|---|
| original lint | 0; no timeout | [command + result](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/qualification/5197fcd16058-20261020T020211206229Z/commands/original_lint/run.json>) | [stdout](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/qualification/5197fcd16058-20261020T020211206229Z/commands/original_lint/stdout.log>) / [stderr](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/qualification/5197fcd16058-20261020T020211206229Z/commands/original_lint/stderr.log>) |
| original synthesis | 0; no timeout | [command + result](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/qualification/5197fcd16058-20261020T020211206229Z/commands/original_synthesis/run.json>) | [stdout](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/qualification/5197fcd16058-20261020T020211206229Z/commands/original_synthesis/stdout.log>) / [stderr](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/qualification/5197fcd16058-20261020T020211206229Z/commands/original_synthesis/stderr.log>) |
| mutant lint | 0; no timeout | [command + result](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/commands/mutant_lint/run.json>) | [stdout](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/commands/mutant_lint/stdout.log>) / [stderr](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/commands/mutant_lint/stderr.log>) |
| mutant synthesis | 0; no timeout | [command + result](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/commands/mutant_synthesis/run.json>) | [stdout](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/commands/mutant_synthesis/stdout.log>) / [stderr](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/commands/mutant_synthesis/stderr.log>) |

Lint and Yosys show that the changed RTL remains accepted by these tools. They do
not prove algorithmic correctness or functional equivalence. Original structural
evidence is reused from the matching sealed qualification; mutant structural
commands ran for this case.

Other recorded gates pass: unchanged testbench, one changed RTL file, unchanged
environment fingerprint, consistent replay signatures, and exact reverse-patch
restoration. The qualification control changes line 96 in a separate source copy;
it is not this dataset mutation. A repeated invocation of the same frozen plan reused
this published pending case and executed zero additional mutations.

For full structured detail, open [case.json](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/case.json>),
[original outcome](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/original.json>),
[mutant run 1 outcome](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/mutant_1.json>),
[mutant run 2 outcome](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/mutant_2.json>),
[mutant run 3 outcome](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/mutant_3.json>), and
[restored outcome](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/restored.json>).

## 7. What was automatic, and what required manual work?

The Python workflow handled frozen-input validation, AST mapping, exact patching,
qualified execution, three mutant runs, reversal/restoration, hardware checks,
publication, integrity auditing, and duplicate protection.

Codex manually selected the repository, prepared/tested its manifest and checker,
and authored saved coding-model responses. The first constant-site response was
rejected before execution by unsupported PyVerilog function syntax. One manually
selected fallback at the quarter-round site produced this case. The shared mutation
engine and upstream sources were not relaxed or rewritten to bypass that rejection.
No live Hermes model session or BaruaLabs execution was performed.

This is therefore evidence of the Python agent/runner integration on another real
repository, with manually assisted setup and response authoring. Your case decision
does not certify autonomous repository admission or a live Hermes deployment.

## 8. What should you approve, request changes for, or reject?

Read sections 2–4 first. Then use the validation tables and linked evidence for any
point you want to check. The review is about the suitability of **this one case**.

| Review question | Evidence supplied | Decision for you |
|---|---|---|
| Is the intended operation clearly addition? | Original RTL, dependency explanation, quarter-round reference | Agree, or identify a requirement concern |
| Is the patch restricted to the proposed defect? | Complete patch; original/buggy/restored source links; one-byte comparison | Agree, or identify an unwanted edit |
| Does the existing unchanged checker expose the bug? | First expected/actual block and all fifteen checkpoint outcomes | Agree, or question the oracle/stimulus |
| Are failure and recovery reproducible? | Three same-mutant runs, restored PASS and source identity, logs | Agree, or request a specific additional check |
| Is this type of case worth retaining? | Clearly synthetic, broad functional arithmetic fault; known scope/limits | Accept, request revision, or reject |

A reasonable limitation to consider is that this bug fails every existing vector,
so it is a strongly exposed example. It does not by itself demonstrate subtle
activation behavior or localization difficulty. ChaCha and SHA-256 also share the
catalog's Secworks crypto lineage; final dataset splits must respect that relation.
Coverage, qualified netlist source mapping, later-block/counter behavior, and
full-protocol verification were not established by this case.

The project user completed this review and explicitly approved the case. The
separate acceptance receipt records that decision; the questions above are retained
as the review checklist, and no further approval is required for this case.

## 9. Evidence identity and scope of this document

| Item | Identity |
|---|---|
| Upstream commit | `7eaba360df9fed9fc2db98d5f3df81cf01e5b604` |
| Case ID | `chacha-cf9ca6a8bc3bf5b4` |
| Published manifest hash | `0995cd3506bfdfd949daa1796871acd15fd2f1dd14ef071f79ab550ed7671bb1` |
| Original/restored changed-file hash | `d6bef8c91bba0f113fcf3c69cd38aa56b3b788956e6dbcbbb2f760641e2dff65` |
| Mutated changed-file hash | `232728d2303a3baab2ed18d4f79ed0a95eb9b6136c3cec0af683f31495bfa089` |
| Testbench hash, all three source snapshots | `fb17ed21e761bf67d89d4adca6c2cb810d24b1eff37cb76fd3f61e25e16018cb` |

The original sealed [execution review summary](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/REVIEW.md>) and
[manifest](</Users/simulbarua/Work/ml_projects/RTLProbe/rtlprobe-data/outputs/chacha/cases/chacha-cf9ca6a8bc3bf5b4-20261020T020419451455Z/manifest.json>) remain intact. This expanded document is
outside that immutable bundle. It is a human-readable explanation of the existing
records, not new simulation evidence, a changed proposal, or an acceptance event.
The [trial report](</Users/simulbarua/Work/ml_projects/RTLProbe/github/rtlprobe/docs/RTLProbe_ChaCha_Agent_Trial_2026-10-19.md>)
contains the full setup history, costs, software-test results, and reproduction
locations. Decision: retain this case as `accepted_core`. No open review decision
or further review action remains for this case; workflow limitations still apply.
