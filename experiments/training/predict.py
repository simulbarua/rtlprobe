"""
Load saved models from a training run and rank the candidates of a package.

    python predict.py --package PATH --run TRAIN_RUN_DIR --out NEW_DIR
    python predict.py --package PATH --run TRAIN_RUN_DIR --out NEW_DIR --samples ID1 ID2 --evaluate

Features are rebuilt from evidence only with the same feature version and
frozen encoder, and the saved training-only preprocessing is applied. The
run refuses a feature version, encoder or column list that differs from the
one the models were trained with. Output per condition: predictions.jsonl
(sample_id, candidate_id, path, line, model, seed, score, rank) and
top10.md. Labels are read only with --evaluate.
"""

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np

import embed
import evaluate
import features
import loader
from run_baseline import DEFAULT_EMB_CACHE, build_features, load_model, prediction_rows, score_model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--run", required=True, help="output folder of run_baseline.py")
    ap.add_argument("--out", required=True)
    ap.add_argument("--conditions", nargs="+", default=None, help="default: all conditions in the run")
    ap.add_argument("--models", nargs="+", default=None, help="default: all models in the run")
    ap.add_argument("--seeds", nargs="+", type=int, default=None, help="default: all seeds in the run")
    ap.add_argument("--samples", nargs="+", default=None, help="default: every sample in the package")
    ap.add_argument("--evaluate", action="store_true", help="also score against the package labels")
    ap.add_argument("--emb-cache", default=str(DEFAULT_EMB_CACHE))
    a = ap.parse_args()

    run_dir, out = Path(a.run), Path(a.out)
    if out.exists():
        sys.exit(f"output directory exists, refusing to overwrite: {out}")
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    if run["feature_version"] != features.FEATURE_VERSION:
        sys.exit(f"models use {run['feature_version']}, this code builds {features.FEATURE_VERSION}")
    if run["encoder"] != embed.IDENTITY:
        sys.exit("frozen encoder identity differs from the one used in training")
    pkg = loader.EvidencePackage(a.package)
    samples = a.samples or pkg.sample_ids
    unknown = set(samples) - set(pkg.sample_ids)
    if unknown:
        sys.exit(f"unknown samples: {sorted(unknown)[:3]}")
    if run["result_label"] == "in_sample_smoke_test":
        print("note: these models come from an in-sample smoke test (trained on development cases)")
    out.mkdir(parents=True)
    encoder = embed.FrozenEncoder(a.emb_cache)
    labels = loader.load_labels(a.package)[0] if a.evaluate else None

    summary = {"training_run": str(run_dir.resolve()), "package": str(Path(a.package).resolve()),
               "samples": samples, "evaluated": a.evaluate, "conditions": {}}
    for cond in a.conditions or list(run["conditions"]):
        rows, _, where = build_features(pkg, cond, encoder)
        keep = np.array([r["sample_id"] in samples for r in rows])
        rows = [r for r, k in zip(rows, keep) if k]
        X, names = features.matrix(rows, cond)
        kinds = np.array([r["syntax_kind"] for r in rows])
        sid = np.array([r["sample_id"] for r in rows])
        keys = [(r["sample_id"], r["candidate_id"]) for r in rows]
        cdir = out / cond
        cdir.mkdir()
        preds, res = [], {}
        for name in a.models or run["models"]:
            for seed in a.seeds or run["seeds"]:
                saved = joblib.load(run_dir / cond / f"{name}_seed{seed}.joblib")
                if saved.get("feature_names", run["conditions"][cond]["features"]) != names:
                    sys.exit(f"{cond}/{name}/seed{seed}: feature columns differ from training")
                m = load_model(name, saved["model"])
                score = score_model(name, m, saved["preprocessor"], X, kinds)
                prows = prediction_rows(keys, where, cond, name, seed, "predict", score, sid)
                evaluate.check_predictions(prows, keys)
                preds.extend(prows)
                if labels is not None:
                    y = np.array([int(c in labels[s]) for s, c in keys])
                    res.setdefault(name, []).append({"seed": seed, **evaluate.summarise(evaluate.per_case(np.asarray(score), sid, y))})
        with open(cdir / "predictions.jsonl", "w", encoding="utf-8") as f:
            for p in preds:
                f.write(json.dumps(p) + "\n")
        md = [f"# Top 10 candidates per sample: {cond}", ""]
        for name in a.models or run["models"]:
            seed = (a.seeds or run["seeds"])[0]
            md += [f"## {name}, seed {seed}", ""]
            for s in samples:
                top = sorted((p for p in preds if p["sample_id"] == s and p["model"] == name and p["seed"] == seed),
                             key=lambda p: (p["rank"], p["path"], p["line"]))[:10]
                md += [f"**{s}**", "", "| Rank | File | Line | Score |", "|---|---|---|---|"]
                md += [f"| {p['rank']} | {p['path']} | {p['line']} | {p['score']:.4f} |" for p in top] + [""]
        (cdir / "top10.md").write_text("\n".join(md), encoding="utf-8")
        summary["conditions"][cond] = {"rows": len(rows), "metrics": res}
        print(f"{cond}: {len(rows)} candidates ranked")
        for name, per in res.items():
            m = {k: np.mean([p[k] for p in per]) for k in ("top1", "top5", "top10", "mrr")}
            print(f"  {name:<7} top-1 {m['top1']:.2f}  top-5 {m['top5']:.2f}  top-10 {m['top10']:.2f}  MRR {m['mrr']:.3f}")
    (out / "predict.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
