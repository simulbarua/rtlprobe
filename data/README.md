# Dataset records

This repository directory currently contains documentation only. The active Python
runner stores dataset manifests, patches, labels, reviews, approvals, and state under
the explicitly configured external data root. See [execution layout](../docs/execution-layout.md).
This guide documents the record types and their retention requirements.
Organize subdirectories as those record formats are implemented.

Small reviewed metadata may be version controlled. Large raw/processed datasets
and local controller state are ignored under `raw/`, `processed/`, and `state/`;
retain necessary data through separately managed storage and backups. This
directory currently contains documentation only.

Keep ground truth, fixes, mutation metadata, and review material separate from
localization-model inputs. Group dataset splits by qualified design/repository
lineage to avoid leakage. Reference generated evidence under `outputs/` using run
identities and hashes rather than copying logs and binaries into metadata.

Preserve sealed records and hash-bound approvals. A functional failure by itself
does not establish an accepted dataset case.
