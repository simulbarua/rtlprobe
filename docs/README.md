# Project documentation

Keep requirements, architecture, configuration contracts, dataset methodology,
research notes, experiment reports, limitations, and recorded decisions here.
Distinguish approved decisions, proposals, historical observations, and freshly
verified findings. Link research claims to primary sources.

## Repository catalog

[Repository catalog spreadsheet](RTLProbe_Repository_Catalog.xlsx) lists candidate
repositories and proposed pilot/split selections. Catalog status is not proof of
testbench qualification or dataset admission. Agents should consult this catalog
before searching for additional repositories; execution still requires an explicit
target manifest and fresh qualification.

Imported unchanged on October 19, 2026 from the shared project-workspace
`docs/RTLProbe_Repository_Catalog.xlsx` identified by the approved mutation plan.
The separate historical `documents/catalogs/` copy was not used. This copy is now
the repository's catalog; future repository edits should update it here.

For human approval, start with the [detailed ChaCha case review](reviews/chacha-cf9ca6a8bc3bf5b4.md).
The [ChaCha agent trial report](RTLProbe_ChaCha_Agent_Trial_2026-10-19.md) records
the repository setup, workflow results, and remaining manual integration steps.

Record the relevant revision, environment, commands, evidence references, and
scope when reporting experiments. Preserve historical results rather than
rewriting them as claims about a new environment.

Existing tooling documentation remains at its original locations:

- [Tooling setup and usage](../tooling/README.md)
- [Pipeline findings](../tooling/FINDINGS.md)
- [Previously tried datasets](../tooling/DATASETS.md)

Use [`../meetings/`](../meetings/README.md) for dated team and advisor notes. Keep
agent implementation and model-provider documentation in the separate agents
repository.
