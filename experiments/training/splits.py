"""
Split reader. Two modes, chosen explicitly:

  dev-smoke  Train and score on the same development_only cases. Results are
             labelled "in_sample_smoke_test" and are never validation or test.
             There is no validation partition in this mode.
  held-out   Requires a frozen split manifest from the dataset owner and
             refuses to run without one. The manifest names train, optional
             validation, and test samples:

               {"split_id": "...", "train": [...], "validation": [...], "test": [...]}

             It refuses: unknown or duplicated samples, a sample in two
             partitions, any development_only / final-test-ineligible sample
             in test, and any grouping key (lineage, design, related site,
             operator template) shared between ANY two partitions.

Validation cases are scored and reported separately from test. The current
models use fixed settings, so validation is not used for tuning or early
stopping (see LIMITATIONS.md).
"""

import json
from itertools import combinations
from pathlib import Path

GROUP_KEYS = ("lineage_group", "design_group", "related_site_group", "operator_template_group")
PARTITIONS = ("train", "validation", "test")


class SplitError(ValueError):
    pass


def dev_smoke(sample_ids, groups):
    bad = [s for s in sample_ids if groups[s]["split"] != "development_only"]
    if bad:
        raise SplitError(f"dev-smoke mode is only for development_only samples: {bad[:3]}")
    return {"mode": "dev-smoke", "result_label": "in_sample_smoke_test",
            "train": list(sample_ids), "validation": [], "test": list(sample_ids)}


def held_out(manifest_path, sample_ids, groups):
    if not manifest_path:
        raise SplitError("held-out mode needs a frozen split manifest; none was given. "
                         "Use --mode dev-smoke for the development starter package.")
    m = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    parts = {p: list(m.get(p) or []) for p in PARTITIONS}
    if not parts["train"] or not parts["test"]:
        raise SplitError("split manifest needs non-empty 'train' and 'test' lists")
    for p, ids in parts.items():
        if len(set(ids)) != len(ids):
            raise SplitError(f"duplicate sample in {p}")
    named = set().union(*map(set, parts.values()))
    unknown = named - set(sample_ids)
    if unknown:
        raise SplitError(f"split manifest names unknown samples: {sorted(unknown)[:3]}")
    for a, b in combinations(PARTITIONS, 2):
        if set(parts[a]) & set(parts[b]):
            raise SplitError(f"a sample is in both {a} and {b}")
    for s in parts["test"]:
        if groups[s]["split"] == "development_only" or not groups[s].get("final_test_eligible"):
            raise SplitError(f"{s} is development_only / not final-test eligible")
    for key in GROUP_KEYS:
        for a, b in combinations(PARTITIONS, 2):
            shared = ({groups[s].get(key) for s in parts[a]} & {groups[s].get(key) for s in parts[b]}) - {None}
            if shared:
                raise SplitError(f"{a} and {b} share {key}: {sorted(shared)[:2]}")
    return {"mode": "held-out", "result_label": "held_out_test", "split_id": m.get("split_id"),
            "manifest": str(manifest_path), **parts}
