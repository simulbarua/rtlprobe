# Dataset records

Keep curated dataset manifests, reconstructable mutation patches, causal labels,
review and acceptance records, and train/validation/test split definitions here.
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
