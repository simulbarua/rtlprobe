# Specification store: rules

Adopted with the direction decision of 2026-10-23 (decision record,
section 2). Each target may carry a `spec/` directory beside its
`config.json`. The store is written by the project owner or a reviewer
**before and independently of mutation planning**, is byte-identical
across every case of the target, and never mentions a mutation site,
operator, or control mutation. The one-sentence `specification.requirement`
fields in existing manifests predate this rule and are not copied into the
store; the SHA-256 manifest's sentence in particular was written around the
control mutation and names the operation its operator breaks.

Layout:

```text
targets/<id>/spec/
  README.md          provenance, license, and what was extracted
  sources.json       documents: url, version, retrieval date, sha256, license,
                     redistributable (true/false); non-redistributable sources
                     are referenced by section, never stored (see below)
  sections/<n>.md    extracted sections, each with source and section id
  requirements.jsonl one record per requirement: id, source, section, text,
                     classification (documented_requirement | repository_claim |
                     inferred_from_rtl_and_checker), rtl_regions, checkpoints
  schema.json        the requirements record schema
```

The localizer receives the store only in specification-enabled conditions
(decision record, section 4). The store is part of the sanitized export's
allowlist and is subject to the same leakage grep as other exports.

## Sources without a redistribution grant

Decision of the project user, 2026-10-23, after the ChaCha curation found
that Bernstein's 2008 ChaCha paper carries no license: the store never
contains text from a source that lacks an explicit redistribution grant,
not even short excerpts, because the runner repository is public and the
project chose not to rely on a fair-use argument. Such a source is still a
legitimate documented source. Its `sources.json` entry keeps
`redistributable: false` and records `quotation_basis: "none; technical
facts restated by the curator with citation"`. Its section files hold only
bibliographic pointers (title, section, page). Requirement records that
rest on it are still `documented_requirement`, but their `text` is the
curator's own neutral statement of the technical fact the source
establishes, followed by the citation in `notes`; it must not reproduce
the source's sentences. The same uniformity rule applies: peers restated
alike. Licensed sources (US Government works, IETF Trust provisions, BSD
or similar) are quoted verbatim as before.
