# SHA-256 specification store

Status: curated, awaiting independent review; not frozen.
Curator: Codex. Curation and retrieval date: 2026-10-23 (America/Los_Angeles).

## Sources and provenance

FIPS PUB 180-4, August 2015, NIST, is the sole normative source. Its source
URL, PDF SHA-256, and retrieval date are in `sources.json`. The PDF is a
US Government work, public domain in the United States; the attributed
section extracts may be stored. It was retrieved into
`/Users/simulbarua/Work/ml_projects/RTLProbe/local/reference/sources/fips180-4/NIST.FIPS.180-4.pdf`.

The original Secworks README, RTL, and testbench use BSD-2-Clause terms.
The permitted RTL headers state the redistribution conditions. The README
claims are classified separately from standard requirements. No RTL source
is reproduced here. The pinned revision is `837c5cc396f001d18f2c765721c585716eb439ae`.

All cited original-source line numbers refer to:
`/Users/simulbarua/Work/ml_projects/RTLProbe/local/rtlprobe-data/outputs/sha256/qualification/fbe1e8a54d45-20261020T010201669067Z/original/`.

The three RTL files have identical SHA-256 values across all 11 available
qualification snapshots. The cross-check read only these three filenames
under `qualification/*/original/src/rtl/`.

| File | Original RTL SHA-256 |
|---|---|
| `sha256_core.v` | `81ea4b865b09ab42034ada6acfeaa2ea2880d39918878aaaa816852677840192` |
| `sha256_w_mem.v` | `0b4de636364625e34e771bb26363d24f4a4bcae6579d0f8cd3e86d7e5c14354a` |
| `sha256_k_constants.v` | `78a9600a6968eb0dc04a3a9fdc6329d3b503044b5a2561263b1cdab18f657007` |

These are source provenance hashes. The freeze hashes of the store itself are
in the Freeze section at the end of this file.

## Extracted sections

- `01-4.1.2-functions.md`
- `02-4.2.2-constants.md`
- `03-5.3.3-initial-hash.md`
- `04-6.2-sha256.md`
- `05-6.2.1-preprocessing.md`
- `06-6.2.2-hash-computation.md`

Printed page numbers and one-based PDF page numbers appear in each extract.
Text was extracted with pypdf in `/tmp/spec-curation-venv`; lost equations
were restored by reading the PDF page images. Repairs are explicitly marked.
Subscripts use `_`, superscripts use `^`, Σ and σ retain distinct meanings,
`∧`, `⊕`, and `¬` denote bitwise AND, XOR, and complement, and `∥` denotes
concatenation. ROTR and SHR retain the standard's rotate-right and
logical-right-shift notation. Section 6.2 contains only its introductory
text; its two subsections have separate files. All schedule and hash
computation equations are included, with none omitted.

## Checked scope and coverage summary

The four checkpoint names are `tc1`, `tc2_block1`, `tc2_block2`, and `issue9`.
The bench checks one prepared block, both results of a two-block sequence,
and only the final result of a nine-block sequence. It holds mode at 1.
It waits on ready and compares the complete 256-bit digest. Padding is
supplied by the caller. No alternate-mode or wrapper behavior is claimed.

`coverage.json` records the exact union of inclusive line regions and its
complement for each file. Counts include physical comment and blank lines
inside complete blocks; they are not simulation coverage measurements.

| RTL file | Covered lines | Uncovered lines | Total lines |
|---|---:|---:|---:|
| `src/rtl/sha256_core.v` | 408 | 146 | 554 |
| `src/rtl/sha256_w_mem.v` | 156 | 85 | 241 |
| `src/rtl/sha256_k_constants.v` | 75 | 59 | 134 |

All statements that compute the compared values, along with storage,
widths, connections, round sequencing, and completion logic, lie in a
mapped region. Whole blocks can also contain assignments outside the
checked scope: SHA-224 branches, register reset values overwritten before
use, and digest_valid logic are not independently verified by the bench.

## Uncovered ranges

### `src/rtl/sha256_core.v`

- `1-41`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `56-60`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `61-68`: SHA-224 initial constants; the testbench holds mode at SHA-256.
- `69`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `78`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `80`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `84-88`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `124`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `130`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `134`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `138-142`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `152`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `155`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `157`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `160`: Unused w_round declaration; round selection is connected directly to t_ctr_reg.
- `162-166`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `171-172`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `184-188`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `190`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `193`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `195-202`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `264-270`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `323-329`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `343-349`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `363-370`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `437-444`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `462-468`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `549-554`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.

### `src/rtl/sha256_w_mem.v`

- `1-41`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `53-57`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `76-80`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `83-87`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `89-96`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `130-137`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `145-152`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `237-241`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.

### `src/rtl/sha256_k_constants.v`

- `1-40`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `45-48`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `50-54`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `56-60`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.
- `130-134`: Comments, blank lines, compilation directive, or module delimiter; no independent value computation.

## Curator decisions

- Eight initial-value records use identical mapping granularity; one table
  record contains all 64 round constants. One record contains all eight
  working-variable updates. All eight digest additions are likewise together.
- Each temporary sum is quoted completely, including every term and addition.
  A common modulo-2^32 record applies to every arithmetic sum. All six
  Boolean functions and both schedule formulas receive records.
- Lowercase `big_sigma0` and `big_sigma1` IDs distinguish Σ from σ while
  respecting the existing lowercase-only ID schema. The schema is unchanged.
- The 16-word schedule window is mapped through its whole load/shift,
  storage, and selection blocks for both formulas. The window relationship
  is an implementation explanation in notes, not additional standard text.
- Whole sequential and combinational blocks are retained, even where they
  include reset values or alternate-mode branches not separately checked.
  The uncovered complement consists of noncomputational text, unused
  w_round, and standalone SHA-224 constants; no arithmetic statement used
  by a compared SHA-256 digest is deliberately excluded.
- Checkpoint associations identify exercised dependencies, not a proof that
  each possible change to a mapped line is distinguishable by these vectors.
  Core arithmetic maps to all four checkpoints. Chaining records use
  tc2_block1, tc2_block2, and issue9 to describe the complete checked sequence;
  continuation itself is observed at the latter two checkpoints.
- ready and digest_valid are separate inferred records. The latter has no
  checkpoints because it is wired and displayed but never asserted by the
  testbench. Exact latency and every handshake transition are not checked.
- The single-block task holds init through its comparison. Later tasks pulse
  init/next for one period. No uniform pulse protocol is inferred beyond
  these observed sequences; simultaneous requests are outside scope.
- Added `original-rtl-and-testbench` as a third source key for inferred
  records, so those statements are not attributed to the README or NIST.
  Only the standard is normative. Repository records cover the README's
  interface widths and caller-supplied padding.
- Section 6.2.1 is retained as standard context. No padding implementation
  requirement is assigned to this core. Length bounds describe the standard,
  not an exhaustive set of tested message lengths.
- No exact cycle-latency claim is taken from the README's platform results.
  The bench waits for completion without a latency comparison. Reset is
  described only to the extent exercised before the supplied sequences.

## Validation and review status

All 34 nonempty JSONL lines validated against `schema.json` using the existing
dataset Python environment: `schema ok`. The required vocabulary scan returned
no matches. Additional checks confirmed unique IDs, known sources and checkpoints,
valid ranges, complete coverage partitions, the uncovered-statement audit,
all eight initial values, all 64 constants, and six section headers.


Reviewed and frozen by the owner on 2026-10-23; see Freeze below. No
configuration edit was made by the curator.

## Freeze

Frozen 2026-10-23 (America/Los_Angeles) by the project owner after review of the
record set, the uncovered ranges, the curator decisions, and the extracted
round equations against the standard. From this point the store changes only
by a logged decision in the project change log, and never between cases of
this target. Any edit must update this table and the change log together.

| File | SHA-256 |
|---|---|
| `requirements.jsonl` | `301e8e75ec62969be62cea26e932a6bd825698f7c0e335a34cfd7c7aed5f0e4e` |
| `sections/01-4.1.2-functions.md` | `3ad7b14cf9c726f3cb3987ce08b1cc48ebca3aec36a1abf69471335b7a43a3fe` |
| `sections/02-4.2.2-constants.md` | `cf373e27c11ed5c9083a6092b1d06f7df62bcbb3862525400673439642af01b8` |
| `sections/03-5.3.3-initial-hash.md` | `3fe8241bc876c03d07e93520afd700cd449b259eb2ca68b4b32143448cced22f` |
| `sections/04-6.2-sha256.md` | `dd0210c6da9bb78b4af63d322c4d667b06b68ab24cd53ef95e42e61cb90778e9` |
| `sections/05-6.2.1-preprocessing.md` | `6f7ae6b0c4e100c5aef00456fed1750cb677417603079231e1a745689091aedf` |
| `sections/06-6.2.2-hash-computation.md` | `4ed707f8828aa88d3038ed0701ea0e95af4bd0d8ab309ddd6323b3d59e750ae5` |
| `coverage.json` | `9bfde76c2edca228b01fec36c36d08cd4aa1b57a87ce16ee8a63d05786a7ade1` |
| `sources.json` | `54ff961c47d5bdbddfc49cb9956c23065d5b0225bd62758433cfa14098fc6000` |
