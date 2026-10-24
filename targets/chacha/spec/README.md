# ChaCha specification store

Status: scaffold created 2026-10-23. No sections extracted yet; no
requirement records yet. The upstream core predates RFC 8439 and exposes
configurable rounds and key sizes; requirement records must say which RFC
statements apply to which configuration the existing bench checks (fifteen
known-answer comparisons, 128/256-bit keys, 8/12/20 rounds) and map them to
`src/rtl/chacha_core.v` and `src/rtl/chacha_qr.v` regions and to the
`case01_tc1_1` to `case15_tc8_1` checkpoints. SIGMA and TAU constants are
repository claims unless tied to the RFC text.

Rules: see `../../SPEC_STORE.md`. Do not mention any mutation site. The
record set must be identical across all ChaCha cases.
