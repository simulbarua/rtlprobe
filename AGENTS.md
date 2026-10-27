# Working in RTLProbe

This is the shared capstone implementation repository. Keep its documentation
useful to contributors who have only this checkout.

## Documentation ownership

- Keep maintained setup, architecture, CLI/configuration contracts, dataset
  methodology, target/checker limitations, and reproducible research methods and
  results here. Update the relevant guide when behavior changes.
- Put agent session reports, implementation/diff reports, ownership audits,
  work orders, task checklists, model-provider instructions, orchestration notes
  and individual curator review dossiers in the separate `rtlprobe-agents`
  repository. Its `project/reports/` directory owns development reports.
  Do not create such files under this repository's `docs/`, `outputs/`, or a
  renamed reports directory. If the agent checkout is unavailable, summarize
  development work in the response rather than placing a report here.
- Distinguish public capstone experiments/results from assistant work history.
  Describe the final behavior, reproduction commands and known limits in
  contributor guides; session chronology, review conversations and work-in-progress
  diffstats belong in the agent repository.
- Use repository-relative links for runner files. Do not require a particular
  parent checkout, local user path, agent configuration, or agent repository to
  use the runner. A brief external-agent integration pointer is sufficient.
- Bulk generated artifacts, labels, patches, case dossiers and acceptance
  records belong in the configured external data/evidence roots. Existing
  hash-bound validation archives and test fixtures must retain their bytes and
  provenance; do not edit them to update documentation links or status wording.
- Treat dated evidence as historical observations, not current qualification.
  Check executable registries/manifests before stating current approval or
  target support. Never invent test, simulation or model results.

See [the documentation index](docs/README.md) for the maintained guides.
