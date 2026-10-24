#!/usr/bin/env python3
"""Derive symptom, difficulty, and review-priority annotations for cases.

Append-only sidecars under <data_root>/data/annotations/<case_id>.json, computed
from sealed case evidence that is never modified. Lives in scripts/ so it does
not enter the runner fingerprint (which covers rtlprobe/*.py and *.json).

Every annotation is a transparent component field; there is no single opaque
difficulty score. Fields that need evidence a bundle does not hold (traces,
candidate universes) are written as "unavailable" with the reason.

Usage: annotate_cases.py --data-root /abs/path [--rewrite]
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ANNOTATION_VERSION = "annotation-2"
FIRST_N_PER_PAIR = 5  # decision record section 5a default


def load(p):
    return json.loads(Path(p).read_text())


def bit_fraction(expected, actual):
    if any(c in actual.lower() for c in "xz"):
        return None
    e, a = int(expected, 16), int(actual, 16)
    return bin(e ^ a).count("1") / (len(expected) * 4)


def differing_words(expected, actual, width_hex=8):
    if any(c in actual.lower() for c in "xz") or len(expected) != len(actual):
        return None
    return sum(1 for i in range(0, len(expected), width_hex)
               if expected[i:i + width_hex].lower() != actual[i:i + width_hex].lower())


SVA_PATTERNS = ("assert property", "assume property", "cover property", "`ASSERT(", "`ASSERT_")


def intent_sources(root, code_root, record, case_dir):
    """What sources of intended behavior exist for this case, split into what the
    localizer may see (availability) and what only the evaluator may see (the
    requirement the mutation violates)."""
    cfg = load(case_dir / "fingerprint.json")["inputs"]["config"]
    # Older bundles predate target_id/test_metadata; resolve the target from the
    # current manifests by design_id and borrow its test_metadata for display only.
    target_id = cfg.get("target_id")
    current = None
    for mp in (code_root / "targets").glob("*/config.json"):
        m = load(mp)
        if (target_id and m.get("target_id") == target_id) or (not target_id and m.get("design_id") == record.get("design_id")):
            current, target_id = m, m.get("target_id")
            break
    if current and "test_metadata" not in cfg:
        cfg = {**cfg, "test_metadata": current.get("test_metadata", {}), "_test_metadata_source": "current manifest, not the sealed one"}
    spec_dir = code_root / "targets" / (target_id or "_none") / "spec"
    sections = sorted(p.name for p in (spec_dir / "sections").glob("*.md")) if spec_dir.exists() else []
    req_path = spec_dir / "requirements.jsonl"
    requirements = [json.loads(l) for l in req_path.read_text().splitlines() if l.strip()] if req_path.exists() else []
    sources = load(spec_dir / "sources.json") if (spec_dir / "sources.json").exists() else {}
    buggy = case_dir / "rtl" / "buggy"
    tb_text = (buggy / cfg["testbench"]).read_text(errors="ignore") if (buggy / cfg["testbench"]).exists() else ""
    rtl_text = "\n".join((buggy / r).read_text(errors="ignore") for r in cfg.get("rtl", []) if (buggy / r).exists())
    sva_tb = sum(tb_text.count(pat) for pat in SVA_PATTERNS)
    sva_rtl = sum(rtl_text.count(pat) for pat in SVA_PATTERNS)
    docs = [f for f in cfg.get("collateral", []) if f.lower().startswith("readme")]
    mutated_path = record["proposal"]["path"]
    mutated_line = record["proposal"]["target"]["line"]
    violated = [r["id"] for r in requirements
                if any(rg.get("path") == mutated_path and _line_in(mutated_line, rg.get("lines", ""))
                       for rg in r.get("rtl_regions", []))]
    documented = [k for k, v in sources.items() if v.get("redistributable") is True and v.get("classification_of_claims") is None]
    return {
        "model_visible": {
            "documented_specification": {
                "available": bool(sections) and bool(requirements),
                "sources_identified": sorted(sources.keys()),
                "documented_sources": documented,
                "sections_extracted": len(sections),
                "requirement_records": len(requirements),
                "note": "available only when sections and requirement records exist; the whole target set is exposed, never a per-case subset",
            },
            "repository_documentation": {"available": bool(docs), "files": docs},
            "testbench_checker": {
                "available": True,
                "kind": cfg.get("test_metadata", {}).get("checker"),
                "checkpoints": cfg.get("test_metadata", {}).get("checkpoints"),
                "expected_values_in_log": True,
            },
            "sva_assertions": {"available": (sva_tb + sva_rtl) > 0, "count_in_testbench": sva_tb, "count_in_rtl": sva_rtl},
            "reference_model": {"available": cfg.get("reference_model") == "available",
                                "declared": cfg.get("reference_model", "absent")},
        },
        "curator_only": {
            "violated_requirement_ids": violated,
            "note": ("label-bearing: which requirement the mutation violates; used by the evaluator to grade an "
                     "explanation or a cited requirement, never exported. Empty until requirement records with "
                     "rtl_regions exist for this target."),
        },
    }


def _line_in(line, spec):
    """'340-345' or '341' or '' -> membership."""
    spec = str(spec).strip()
    if not spec:
        return False
    if "-" in spec:
        a, b = spec.split("-", 1)
        return int(a) <= line <= int(b)
    return int(spec) == line


def annotate(root, summary, code_root):
    case_dir = root / summary["case_path"]
    record = load(case_dir / "case.json")
    proposal = record["proposal"]
    mutants = record.get("mutants") or []
    first = mutants[0] if mutants else {}
    checkpoints = first.get("checkpoints") or []
    failed = [c for c in checkpoints if c.get("outcome") == "functional_fail"]
    per_cp = []
    for c in failed:
        per_cp.append({
            "id": c["id"],
            "bit_difference_fraction": bit_fraction(c["expected"], c["actual"]),
            "differing_32bit_words": differing_words(c["expected"], c["actual"]),
            "total_32bit_words": len(c["expected"]) // 8,
        })
    fracs = [x["bit_difference_fraction"] for x in per_cp if x["bit_difference_fraction"] is not None]
    pred = proposal.get("prediction") or {}
    first_failing = failed[0]["id"] if failed else None
    flags = []
    if first_failing and pred.get("first_checkpoint") and first_failing != pred["first_checkpoint"]:
        flags.append("unexpected_first_checkpoint")
    if record.get("prediction_agreement") not in ("confirmed", None):
        flags.append("prediction_disagreement")
    checks = record.get("checks") or {}
    if checks and not (checks.get("restored_pass", True) and checks.get("restored_source_identity", True)):
        flags.append("restoration_anomaly")
    if len(failed) and len(failed) < len(checkpoints):
        flags.append("partial_checkpoint_failure")  # informative, not a defect; worth a look
    return {
        "annotation_version": ANNOTATION_VERSION,
        "case_id": record["case_id"],
        "case_manifest_sha256": summary["case_manifest_sha256"],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "computed_from": "sealed case.json and first mutant run; bundle not modified",
        "design_id": record.get("design_id"),
        "operator_id": (proposal.get("operator") or {}).get("id"),
        "operator_family": proposal.get("family"),
        "lineage_id": proposal.get("lineage_id"),
        "split_group": proposal.get("split_group"),
        "mutated_path": proposal.get("path"),
        "mutated_line": (proposal.get("target") or {}).get("line"),
        "state": summary.get("state"),
        "symptom": {
            "checkpoints_total": len(checkpoints),
            "checkpoints_failed": len(failed),
            "failure_pattern": ("all_checkpoints" if failed and len(failed) == len(checkpoints)
                                else "partial" if failed else "none"),
            "first_failing_checkpoint": first_failing,
            "per_checkpoint": per_cp,
            "bit_difference_fraction_mean": (sum(fracs) / len(fracs)) if fracs else None,
            "bit_difference_fraction_min": min(fracs) if fracs else None,
            "detection_latency_cycles": "unavailable: no trace in the sealed bundle",
            "first_divergent_signal": "unavailable: no paired trace captured",
        },
        "difficulty_components": {
            "symptom_summary_discriminates": bool(fracs) and (min(fracs) < 0.25 or len(failed) < len(checkpoints)),
            "all_output_bits_scrambled": bool(fracs) and min(fracs) >= 0.4,
            "mutation_in_top_module": None,  # filled when a hierarchy map is available
            "candidate_universe_size": "unavailable: computed by the localization extractor, not stored here",
            "note": "components only; no composite score by design",
        },
        "intent_sources": intent_sources(root, code_root, record, case_dir),
        "planner_confidence": proposal.get("confidence"),
        "prediction_agreement": record.get("prediction_agreement"),
        "review": {
            "flags": flags,
            "pair_ordinal": None,       # filled below once all cases are known
            "needs_human_review": None,  # filled below
            "rule": f"first {FIRST_N_PER_PAIR} per operator-and-design pair, any flag, or sampled",
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", required=True, type=Path)
    ap.add_argument("--rewrite", action="store_true", help="overwrite existing annotation files")
    ap.add_argument("--code-root", type=Path, default=Path(__file__).resolve().parents[1],
                    help="RTLProbe checkout holding targets/<id>/spec (default: this repository)")
    args = ap.parse_args()
    root = args.data_root.resolve(); code_root = args.code_root.resolve()
    out_dir = root / "data" / "annotations"
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = [load(p) for p in sorted((root / "data" / "manifests").glob("*.json"))]
    summaries = [s for s in summaries if "case_path" in s]
    annotations = []
    for s in summaries:
        try:
            annotations.append(annotate(root, s, code_root))
        except Exception as exc:  # annotate what we can; never stop the index
            annotations.append({"annotation_version": ANNOTATION_VERSION, "case_id": s["case_id"],
                                "error": f"{type(exc).__name__}: {exc}"})
    # pair ordinal by case directory timestamp (encoded in the path)
    by_pair = defaultdict(list)
    for a, s in zip(annotations, summaries):
        if "error" in a:
            continue
        by_pair[(a["design_id"], a["operator_id"])].append((s["case_path"], a))
    for pair, items in by_pair.items():
        for i, (_, a) in enumerate(sorted(items, key=lambda x: x[0]), 1):
            a["review"]["pair_ordinal"] = i
            a["review"]["needs_human_review"] = bool(i <= FIRST_N_PER_PAIR or a["review"]["flags"])
    written = skipped = 0
    for a in annotations:
        p = out_dir / f"{a['case_id']}.json"
        if p.exists() and not args.rewrite:
            skipped += 1
            continue
        p.write_text(json.dumps(a, indent=2, sort_keys=True) + "\n")
        written += 1
    (out_dir / "index.jsonl").write_text("".join(json.dumps(a, sort_keys=True) + "\n" for a in annotations))
    print(json.dumps({"cases": len(annotations), "written": written, "skipped_existing": skipped,
                      "errors": sum("error" in a for a in annotations), "output": str(out_dir)}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
