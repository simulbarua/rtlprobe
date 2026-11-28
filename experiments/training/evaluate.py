"""
Per-defect ranking evaluation (Simul's README, "Predictions and metrics").

Tie rule (fixed): a tied group of candidates shares the average of the
positions it spans, i.e. the expected rank under random tie-breaking.
Ties with the true line are counted and reported. Metrics are averaged over
defects, never over candidate rows. A case whose true line is not in the
candidate set counts as a miss (all starter cases are mapped).
"""

import math

import numpy as np


def rank_of_positive(scores, positive_mask):
    if not positive_mask.any():
        return math.inf, 0
    s = scores[positive_mask].max()
    better = int((scores > s).sum())
    tied = int((scores == s).sum())
    return 1 + better + 0.5 * (tied - 1), tied - 1


def per_case(scores, case_index, y):
    out = []
    for c in dict.fromkeys(case_index):
        m = case_index == c
        r, ties = rank_of_positive(scores[m], y[m] == 1)
        out.append({"case": c, "rank": r, "ties_with_bug": ties, "n": int(m.sum())})
    return out


def summarise(cases):
    r = np.array([c["rank"] for c in cases], dtype=float)
    rr = np.where(np.isfinite(r), 1 / r, 0.0)
    return {"defects": len(cases),
            "top1": float(np.mean(r <= 1)), "top5": float(np.mean(r <= 5)), "top10": float(np.mean(r <= 10)),
            "mrr": float(rr.mean()), "median_rank": float(np.median(r)),
            "cases_with_ties_at_bug": int(sum(c["ties_with_bug"] > 0 for c in cases)),
            "missed_true_site": int(np.sum(~np.isfinite(r)))}


def random_reference(case_sizes):
    """Exact expectation under a uniformly random order (one true line)."""
    n = np.array(case_sizes, dtype=float)
    harmonic = np.array([sum(1 / k for k in range(1, int(x) + 1)) for x in n])
    return {"defects": len(n), "top1": float(np.mean(1 / n)), "top5": float(np.mean(np.minimum(5, n) / n)),
            "top10": float(np.mean(np.minimum(10, n) / n)), "mrr": float(np.mean(harmonic / n)),
            "median_rank": float(np.median((n + 1) / 2)), "cases_with_ties_at_bug": 0, "missed_true_site": 0}


def output_ranks(scores, case_index):
    """Rank shown in prediction files: 1 + number of candidates in the same
    case with a strictly higher score (tied candidates share the best rank).
    Evaluation uses the average-rank rule above; this is only for listing."""
    ranks = np.zeros(len(scores), dtype=int)
    for c in dict.fromkeys(case_index):
        idx = np.where(case_index == c)[0]
        s = scores[idx]
        ranks[idx] = 1 + (s[None, :] > s[:, None]).sum(axis=1)
    return ranks


def check_predictions(pred_rows, expected_keys):
    keys = [(p["sample_id"], p["candidate_id"]) for p in pred_rows]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate prediction keys")
    if set(keys) != set(expected_keys):
        raise ValueError("predictions do not match the bound candidate universe")
    if not all(math.isfinite(p["score"]) for p in pred_rows):
        raise ValueError("non-finite score")
