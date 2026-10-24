# SHA-256 specification store

Status: scaffold created 2026-10-23. No sections extracted yet; no
requirement records yet. Fill `sources.json` retrieval date and hash when the
document is fetched; extract the sections listed in `sources_of_interest`
into `sections/`; write requirement records that cover the whole scope the
existing testbench checks (single block, double block, nine-block issue),
mapped to `src/rtl/sha256_core.v`, `sha256_w_mem.v`, and `sha256_k_constants.v`
regions and to checkpoints `tc1`, `tc2_block1`, `tc2_block2`, `issue9`.

Rules: see `../../SPEC_STORE.md`. Do not import the manifest's
`specification.requirement` sentence; it was written around the control
mutation. Do not mention any mutation site. The record set must be identical
across all SHA-256 cases.
