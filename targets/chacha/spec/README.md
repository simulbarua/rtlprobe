# ChaCha specification store

Status: curated, awaiting independent review; not frozen.
Curator: Codex. Curation and local retrieval date: 2026-10-23 (America/Los_Angeles).
The owner supplied both published documents locally; their bytes were hashed by
the curator. No network retrieval was performed during this continuation.

## Sources and provenance

RFC 8439 (Yoav Nir and Adam Langley, June 2018) is an informational IRTF
publication. Its IETF configuration uses 20 rounds, a 256-bit key, a 96-bit
nonce, and a 32-bit counter. Six attributed extracts retain its wording,
equations, pseudocode, and block vector. RFC copyright and BCP 78 / IETF Trust
Legal Provisions attribution accompanies each extract. Source file:
`/Users/simulbarua/Work/ml_projects/RTLProbe/local/reference/sources/rfc8439/rfc8439.txt`.

Daniel J. Bernstein's *ChaCha, a variant of Salsa20*, dated 2008-01-28,
provides the named round variants, common quarter round, matrix roles and
ordering, and final addition. Source file:
`/Users/simulbarua/Work/ml_projects/RTLProbe/local/reference/sources/djb-chacha-2008/chacha-20080128.pdf`.
The PDF was inspected with pypdf from `/tmp/spec-curation-venv/bin/python`;
pages 1-5 were also visually inspected. No software was installed.

Under the owner rule adopted 2026-10-23 in `targets/SPEC_STORE.md`,
"Sources without a redistribution grant", no paper sentences or excerpts
are stored, including short excerpts. The paper has no explicit redistribution
grant, and `redistributable` remains false. Its page 2 public-domain statement
concerns software. The four paper-backed requirement records restate technical
facts in the curator's own wording, with title, section, and PDF page citations
in notes. The four paper section files contain bibliographic pointers only,
including the document ID. `quotation_basis` records this adopted treatment.

The pinned README and original RTL/testbench are Secworks BSD-2-Clause
material. README-only claims and observations of the implementation are
classified separately. The revision is
`7eaba360df9fed9fc2db98d5f3df81cf01e5b604`.
Every original RTL and checker line number refers to:
`/Users/simulbarua/Work/ml_projects/RTLProbe/local/rtlprobe-data/outputs/chacha/qualification/5197fcd16058-20261020T020211206229Z/original`.

| Source | SHA-256 of supplied or original file |
|---|---|
| `rfc8439` | `25bef70fbf7a07ff45c2fe4cb7c6ce954eac687413d8610603268b4e4415324c` |
| `djb-chacha-2008` | `654280755b604667419f24d72047e3729655481d2569694125930070f87187f7` |
| `secworks-chacha-readme` | `1124644da2c6028be53fbdf4e25ae69b4d3b75cdde4467a3c26899f01a9d70bb` |

| Original file | SHA-256 |
|---|---|
| `src/rtl/chacha_core.v` | `498bde1d1e83793eb65d37378257e2df8ff9a46da0b783da0b7d2d4f59225844` |
| `src/rtl/chacha_qr.v` | `d6bef8c91bba0f113fcf3c69cd38aa56b3b788956e6dbcbbb2f760641e2dff65` |
| `src/tb/tb_chacha_core.v` | `fb17ed21e761bf67d89d4adca6c2cb810d24b1eff37cb76fd3f61e25e16018cb` |

Only the two named RTL files were read for the cross-snapshot comparison.
Both have identical hashes in these two qualification snapshots:

- `5197fcd16058-20261020T020211206229Z/original/`
- `cc524ec031ce-20261020T020144194492Z/original/`

These are source provenance hashes only. No store freeze hashes have been written.

## Section files

- `01-rfc8439-2.1-quarter-round.md`
- `02-rfc8439-2.2-state-quarter-round.md`
- `03-rfc8439-2.3-block-function.md`
- `04-rfc8439-2.3.1-pseudocode.md`
- `05-rfc8439-2.3.2-block-vector.md`
- `06-rfc8439-2.4-encryption.md`
- `07-djb-abstract-round-variants.md`
- `08-djb-2.1-notation.md`
- `09-djb-2.2-quarter-round.md`
- `10-djb-3.2-matrix.md`
- `11-readme-functionality.md`
- `12-readme-performance.md`

RFC running page headers/footers and excess blank lines were removed; source
wording and diagrams are retained. Section 2.3.1 is pseudocode; 2.3.2 is the
block test vector, correcting the scaffold's section label. Sections 2.1.1
and 2.2.1 are not selected: no separate quarter-round expected-value check
runs in the supplied bench. Section 2.3 spans parts of three printed pages
but is retained as one compact file, preserving the whole state description.
The README files contain only their explicitly identified excerpts.

The RFC 2.3.2 vector is context only: its 96-bit nonce cannot be supplied to
the 64-bit iv port unchanged. None of the fifteen comparisons uses that
vector, and no requirement record claims otherwise.

## Checked scope and checkpoint mapping

The bench calls `run_test_case` fifteen times (lines 530-661). Each call
resets the core, supplies a configuration, pulses init for one clock period,
waits for a rising `data_out_valid`, and compares all 512 output bits
(lines 397-437). `ctr` is tied to zero (lines 78, 124), `next` remains zero,
and `data_in` remains zero (lines 476-478). These are single-block keystream
comparisons. Exact latency, ready, nonzero counter loads, continuation,
counter carry/wrap, and nonzero input-data behavior are not independently
checked. The preliminary `qr_tests` task only displays values; it has no
expected-value assertion and creates no additional checkpoint.

| Checkpoint | Key bits | Rounds | Testbench call line |
|---|---:|---:|---:|
| `case01_tc1_1` | 128 | 8 | 530 |
| `case02_tc1_2` | 128 | 12 | 539 |
| `case03_tc1_3` | 128 | 20 | 548 |
| `case04_tc1_4` | 256 | 8 | 557 |
| `case05_tc1_5` | 256 | 12 | 566 |
| `case06_tc1_6` | 256 | 20 | 575 |
| `case07_tc2_1` | 128 | 8 | 584 |
| `case08_tc2_1` | 256 | 8 | 593 |
| `case09_tc3_1` | 128 | 8 | 602 |
| `case10_tc4_1` | 128 | 8 | 611 |
| `case11_tc5_1` | 128 | 8 | 620 |
| `case12_tc6_1` | 128 | 8 | 629 |
| `case13_tc7_1` | 128 | 8 | 638 |
| `case14_tc7_2` | 256 | 8 | 647 |
| `case15_tc8_1` | 128 | 8 | 656 |

There are ten 128-bit and five 256-bit comparisons; eleven use 8 rounds,
two use 12 rounds, and two use 20 rounds. The eighth call is actually
`TC2, ONE` again despite its display text: the ordered name is therefore
`case08_tc2_1`, and its key is 256 bits. The checkpoint list matches the
permitted configuration projection.

There are 27 records: 11 documented requirements,
2 repository claims, and 14 RTL/checker inferences.
By source: rfc8439: 7, original-rtl-and-testbench: 14, djb-chacha-2008: 4, secworks-chacha-readme: 2.

## Coverage summary

`coverage.json` is the inclusive union of all record regions and its exact
complement for each original RTL file. Counts include comments and blank
lines inside complete blocks; they are source mapping, not measured
execution coverage. Its checkpoint configuration table is derived from the
actual ordered bench calls.

| RTL file | Covered lines | Uncovered lines | Total lines |
|---|---:|---:|---:|
| `src/rtl/chacha_core.v` | 564 | 145 | 709 |
| `src/rtl/chacha_qr.v` | 54 | 64 | 118 |

Every computational statement used to form a compared block is mapped,
along with declarations, connections, storage, round sequencing, and output
capture. Whole blocks also include unexercised branches. In particular,
next handling, counter increment/carry, ready, and restart from CTRL_DONE
are physically mapped but are not claimed to be checked. Records solely
about these behaviors have empty checkpoint lists. The repository cycle
claim likewise has no timing checkpoint.

## Uncovered ranges

### `src/rtl/chacha_core.v`

- `1-41`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `61-66`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `69`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `70`: Unused NUM_ROUNDS constant; the active loop uses the rounds input.
- `71`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `76`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `81`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `87-93`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `99-103`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `143-147`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `149`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `153`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `189-193`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `241-245`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `249-257`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `309-315`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `370-375`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `486-495`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `520-526`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `544-550`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `568-574`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `603-608`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `705-709`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.

### `src/rtl/chacha_qr.v`

- `1-43`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `54-57`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `62-66`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `71-77`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `114-118`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.

## Curator decisions

- One complete quarter-round record includes all four additions, all four
  XORs, all four rotations, and all four returned words. SIGMA and TAU each
  use one four-word record with the same initialization-block granularity.
  Key expansion covers all eight destination words in each mode. Matrix
  initialization and final addition each cover all sixteen words; counter
  loading and increment each describe both halves together.
- Every arithmetic/sequence mapping uses whole blocks. Register update,
  initialization, state routing, final output, both round counters, block
  counter, and controller are mapped at their complete block boundaries.
  Independent declarations and connections are also mapped where relevant.
- The paper assumes prior Salsa20 knowledge. It does not explicitly print
  TAU values, the 128-bit key repetition rule, or a little-endian byte rule.
  Those details cannot honestly be quoted from it. TAU and 128-bit expansion
  are classified as RTL/checker inferences; precise counter/IV wiring and
  l2b likewise remain inferences. RFC section 2.3 page 8 explicitly confirms
  the original 64-bit nonce and counter widths, while paper section 3.2
  establishes their order. Neither is substituted for the RTL's exact bus
  mapping. No additional Salsa20 source was consulted.
- Paper-backed round-count records cover 8, 12, and 20 uniformly and identify
  the exact checkpoint subsets. The named counts are documented in the
  paper; applying them with this 128-bit expansion is established by the
  original RTL/bench. This distinction is explicit in every such record.
- RFC quotations remain verbatim apart from line wrapping. Their surrounding
  notes distinguish the IETF configuration from common arithmetic used by
  the original variants. Reduced-round final addition is supported by paper
  section 3.2. Applying the RFC byte convention to original 128-bit and
  reduced-round configurations is supported by the RTL/bench, not by an
  explicit paper byte-order statement.
- Checkpoints identify exercised dependencies, not proof that every change
  to a mapped statement would be distinguishable. All-zero counter inputs
  cannot distinguish every counter-loading detail. Zero input data cannot
  establish general plaintext XOR behavior. No additional stimulus or
  reference implementation was run.
- `data_out_valid` participates in every comparison; `ready` does not.
  `next`, counter increment/carry, and exact round-cycle timing have empty
  checkpoint lists. No multi-block behavior is attributed to the fifteen
  single-block comparisons. Reset is described only as exercised before
  requests; individual reset values are not separately asserted.
- README statements about two through 32 rounds and four parallel quarter
  rounds remain repository claims. The five-bit rounds port and untested
  32-round endpoint are noted without inventing an encoding. NUM_ROUNDS is
  unused and intentionally left uncovered. No wrapper timing is inferred.
- The original RTL/testbench source key keeps interface observations separate
  from the README and published documents. The schema is unchanged.
- The owner rule adopted 2026-10-23 prohibits all paper sentences and
  excerpts in this public store, including short excerpts. The four
  paper-backed records restate technical facts with citations. The three
  round-count statements use identical wording except for the variant,
  round count, and double-round count. The matrix statement describes all
  sixteen word positions uniformly. Section files 07-10 contain only
  bibliographic pointers with title, section, PDF page, and document ID.
  The public sources remain in the two designated reference directories.

## Validation and review status

All 27 records validated against the unchanged schema using the existing
dataset Python environment: `schema ok`. Additional checks passed for unique
IDs, exact source quotations after whitespace normalization, all 12 section
headers and excerpts/references, checkpoint groups, valid inclusive ranges,
complete coverage partitions, complete procedural blocks, and the uncovered
statement audit. The required vocabulary scan returned no matches. No configuration change,
annotation action, commit, or push is part of this curation. Independent
review and the owner's freeze remain pending.

Review selection uses Python `random.Random(20261023)`: choose one record from
the paper-source subset in file order, then sample two distinct records from
the remaining records in file order. Selected IDs: `chacha.rounds.count.12`, `chacha.rounds.column`, `chacha.interface.l2b`.
This selects spot checks; it does not constitute independent review.

Revision check for the 2026-10-23 owner rule: only the four paper-backed
records changed, and only their text and notes fields. IDs, classifications,
sources, sections, RTL regions, checkpoints, and coverage remain unchanged.
The store was checked against the supplied paper for reproduced sentences;
none remain. Bibliographic titles and identifiers are retained as citations.

## Freeze

Frozen 2026-10-23 (America/Los_Angeles) by the project owner after review of the
record set, the uncovered ranges, the curator decisions, the four restated
paper-backed records, and the extracted RFC sections. From this point the store
changes only by a logged decision in the project change log, and never between
cases of this target. Any edit must update this table and the change log together.

| File | SHA-256 |
|---|---|
| `requirements.jsonl` | `2a8123be0a48e79420da3845845c7728a418c988ff355be2cd3a37f7ced5c122` |
| `sections/01-rfc8439-2.1-quarter-round.md` | `24e263c758c7f51fe9ec513f48bd2cb1fb75d04516f7ff09b62dcfc1e0d3af78` |
| `sections/02-rfc8439-2.2-state-quarter-round.md` | `3c55dc6878332b6f5f1f52d1ce55419c76e2e1dd25d96bee7a866f4fcc77bd75` |
| `sections/03-rfc8439-2.3-block-function.md` | `002efd72d955638b053b6c141b485ee9101b7653af061d5ca96acc8e6424af2e` |
| `sections/04-rfc8439-2.3.1-pseudocode.md` | `fdaf869579f0e57e60f81d88400cdd487b5be185e45f3f867defc123fe610d2d` |
| `sections/05-rfc8439-2.3.2-block-vector.md` | `073630fd8793f9966d11cf7b734693312600a8656b99cb3186d461968a79921b` |
| `sections/06-rfc8439-2.4-encryption.md` | `c434a7b204241015eb1c61bc71273000a446786b0668990f7fd7e365c98a7728` |
| `sections/07-djb-abstract-round-variants.md` | `7c03056115e1e00e40422ba79c9240b582198f344b07cf9f6903fb3046227d63` |
| `sections/08-djb-2.1-notation.md` | `149a8a68a1aeeea1cf2a892c189ba24ede67731356287cbb2f053e3cf7e0b144` |
| `sections/09-djb-2.2-quarter-round.md` | `c2fe273feb0600e2c14684cf1aab0a790e698a816d5503cf73077c77b381c3cc` |
| `sections/10-djb-3.2-matrix.md` | `108096b4bd696a8ab590277ba68fa6fa0068dec20342f21857fab7e4e45a4b91` |
| `sections/11-readme-functionality.md` | `c9659b775af4c4a4de521915838069d19726007f5a310a0dc368c6f140d7eacf` |
| `sections/12-readme-performance.md` | `12dd10fe9251bdb02e597265fc549de6ef29cd69149f5b7c8b2adde181198ea1` |
| `coverage.json` | `41bb0fd327ce14ec762dc817082f9307dcc3ff247f3e47f5b836c9595531fba3` |
| `sources.json` | `52226d62afbaef131c591e0ba47a44b46460e74e5abc9e3a5d7330ac64ac3bfc` |
