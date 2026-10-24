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
                     are referenced by section, never stored
  sections/<n>.md    extracted sections, each with source and section id
  requirements.jsonl one record per requirement: id, source, section, text,
                     classification (documented_requirement | repository_claim |
                     inferred_from_rtl_and_checker), rtl_regions, checkpoints
  schema.json        the requirements record schema
```

The localizer receives the store only in specification-enabled conditions
(decision record, section 4). The store is part of the sanitized export's
allowlist and is subject to the same leakage grep as other exports.
