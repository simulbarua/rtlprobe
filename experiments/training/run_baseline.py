"""
One entry point: package path + mode (+ split manifest) -> features, trained
models, ranked per-candidate predictions, per-defect evaluation and a report.

    python run_baseline.py --package PATH --out NEW_DIR --mode dev-smoke
    python run_baseline.py --package PATH --out NEW_DIR --mode held-out --split SPLIT.json

The output directory must not exist (nothing is overwritten). Features are
built from evidence only; labels are loaded afterwards, by a separate
function, for training and scoring. Models are trained on the train
partition and scored on validation (if any) and test.
"""

import argparse
import hashlib
import json
import math
import platform
import shutil
import sys
import time
from pathlib import Path

import joblib
import numpy as np

import embed
import evaluate
import features
import loader
import models
import report
import splits

ROOT = Path(__file__).resolve().parent
DEFAULT_EMB_CACHE = Path.home() / ".cache" / "rtlprobe-training" / "unixcoder"


def build_features(pkg, condition, encoder):
    """Evidence-only rows plus a (sample_id, candidate_id) -> (path, line)
    lookup used only for writing predictions, never as a feature."""
    rows_all, metas, where = [], {}, {}
    for sid in pkg.sample_ids:
        view = pkg.view(sid, condition)
        rows, meta = features.build(view, encoder, condition)
        rows_all.extend(rows)
        metas[sid] = meta
        for c in view.candidates:
            where[(sid, c["candidate_id"])] = (c["path"], c["line"])
    return rows_all, metas, where


def features_digest(rows):
    h = hashlib.sha256()
    for r in rows:
        h.update(json.dumps(r, sort_keys=True, default=lambda x: None if isinstance(x, float) and math.isnan(x) else x).encode())
    return h.hexdigest()


def fit_model(name, seed, pre, X, kinds, y, sid):
    if name == "logreg":
        return models.fit_logreg(pre.for_logreg(X, kinds), y, sid, seed)
    if name == "lgbm":
        return models.fit_lgbm(pre.for_lgbm(X, kinds), y, sid, seed)
    return models.fit_mlp(pre.for_logreg(X, kinds), y, sid, seed)


def score_model(name, m, pre, X, kinds):
    if name == "logreg":
        return m.decision_function(pre.for_logreg(X, kinds))
    if name == "lgbm":
        return m.predict(pre.for_lgbm(X, kinds))
    return m.score(pre.for_logreg(X, kinds))


def load_model(name, saved):
    return models.NeuralRanker.from_state(saved) if name == "mlp" else saved


def prediction_rows(keys, where, cond, name, seed, partition, score, sid):
    ranks = evaluate.output_ranks(np.asarray(score, float), sid)
    return [{"sample_id": s, "candidate_id": c, "path": where[(s, c)][0], "line": where[(s, c)][1],
             "condition": cond, "model": name, "seed": seed, "partition": partition,
             "score": float(v), "rank": int(r)}
            for (s, c), v, r in zip(keys, score, ranks)]


def references(X, names, sid, y):
    sizes = [int(np.sum(sid == s)) for s in dict.fromkeys(sid)]
    order_score = -np.arange(len(sid), dtype=float)             # file/line order as emitted
    lex = np.nan_to_num(X[:, names.index("log_overlap")], nan=-1.0)
    return {"random": evaluate.random_reference(sizes),
            "source_order": evaluate.summarise(evaluate.per_case(order_score, sid, y)),
            "lexical_log_overlap": evaluate.summarise(evaluate.per_case(lex, sid, y))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["dev-smoke", "held-out"], required=True)
    ap.add_argument("--split", default=None, help="frozen split manifest (held-out mode)")
    ap.add_argument("--conditions", nargs="+", default=["C0", "C1", "C2", "C3", "C4"])
    ap.add_argument("--seeds", nargs="+", type=int, default=models.DEFAULT_SEEDS)
    ap.add_argument("--models", nargs="+", choices=["logreg", "lgbm", "mlp"], default=["logreg", "lgbm", "mlp"])
    ap.add_argument("--emb-cache", default=str(DEFAULT_EMB_CACHE))
    a = ap.parse_args()

    out = Path(a.out)
    if out.exists():
        sys.exit(f"output directory exists, refusing to overwrite: {out}")
    t0 = time.time()

    pkg = loader.EvidencePackage(a.package)                 # validates integrity + label joins
    groups = loader.load_groups(a.package)
    split = (splits.dev_smoke(pkg.sample_ids, groups) if a.mode == "dev-smoke"
             else splits.held_out(a.split, pkg.sample_ids, groups))
    out.mkdir(parents=True)                                 # only after every check has passed
    shutil.copy2(models.CONFIG_PATH, out / "model_config.json")
    encoder = embed.FrozenEncoder(a.emb_cache)

    run = {"result_label": split["result_label"], "package": str(Path(a.package).resolve()),
           "package_check": pkg.summary, "split": split, "feature_version": features.FEATURE_VERSION,
           "encoder": embed.IDENTITY, "model_config_sha256": models.CONFIG_SHA256,
           "lgbm_params": models.LGBM_PARAMS, "logreg_params": models.LOGREG_PARAMS,
           "mlp_params": models.MLP_PARAMS, "models": a.models, "seeds": a.seeds,
           "python": sys.version.split()[0], "platform": platform.platform(), "conditions": {}}
    scored_parts = [p for p in ("validation", "test") if split[p]]

    labels, _ = loader.load_labels(a.package)              # labels: training/eval only
    for cond in a.conditions:
        rows, metas, where = build_features(pkg, cond, encoder)
        X, names = features.matrix(rows, cond)
        kinds = np.array([r["syntax_kind"] for r in rows])
        sid = np.array([r["sample_id"] for r in rows])
        keys = [(r["sample_id"], r["candidate_id"]) for r in rows]
        y = np.array([int(r["candidate_id"] in labels[r["sample_id"]]) for r in rows])
        mask = {p: np.isin(sid, split[p]) for p in ("train", *scored_parts)}
        tr = mask["train"]
        cdir = out / cond
        cdir.mkdir()
        with open(cdir / "features.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, sort_keys=True) + "\n")

        pre = models.Preprocessor().fit(X[tr], list(kinds[tr]))
        cond_res = {"features": names, "columns": pre.column_names(names), "features_sha256": features_digest(rows),
                    "anchors": sorted({x for m in metas.values() for x in m["anchors"]}),
                    "rows": {p: int(m.sum()) for p, m in mask.items()},
                    "partitions": {p: {"models": {}, "references": references(X[mask[p]], names, sid[mask[p]], y[mask[p]])}
                                   for p in scored_parts}}
        preds = []
        for name in a.models:
            per = {p: [] for p in scored_parts}
            for seed in a.seeds:
                m = fit_model(name, seed, pre, X[tr], kinds[tr], y[tr], sid[tr])
                joblib.dump({"model": m.state() if name == "mlp" else m, "model_name": name, "seed": seed,
                             "condition": cond, "preprocessor": pre, "feature_names": names,
                             "columns": pre.column_names(names), "feature_version": features.FEATURE_VERSION,
                             "encoder": embed.IDENTITY, "model_config_sha256": models.CONFIG_SHA256},
                            cdir / f"{name}_seed{seed}.joblib")
                for p in scored_parts:
                    k = mask[p]
                    score = score_model(name, m, pre, X[k], kinds[k])
                    prows = prediction_rows([kk for kk, b in zip(keys, k) if b], where, cond, name, seed, p, score, sid[k])
                    evaluate.check_predictions(prows, [kk for kk, b in zip(keys, k) if b])
                    preds.extend(prows)
                    cases = evaluate.per_case(np.asarray(score), sid[k], y[k])
                    per[p].append({"seed": seed, **evaluate.summarise(cases), "per_case": cases})
            for p in scored_parts:
                metric_keys = [x for x in per[p][0] if x not in ("seed", "per_case")]
                cond_res["partitions"][p]["models"][name] = {
                    "per_seed": per[p],
                    "mean": {x: float(np.mean([s[x] for s in per[p]])) for x in metric_keys},
                    "sd": {x: float(np.std([s[x] for s in per[p]])) for x in metric_keys}}
        with open(cdir / "predictions.jsonl", "w", encoding="utf-8") as f:
            for p in preds:
                f.write(json.dumps(p) + "\n")
        run["conditions"][cond] = cond_res
        scored = ", ".join(f"{p}={cond_res['rows'][p]} rows" for p in scored_parts)
        print(f"{cond}: {len(names)} features, scored {scored}")

    run["seconds"] = round(time.time() - t0, 1)
    (out / "run.json").write_text(json.dumps(run, indent=1), encoding="utf-8")
    (out / "report.md").write_text(report.markdown(run), encoding="utf-8")
    print(report.console_table(run))
    print(f"\nSaved to {out}  (report.md, run.json, per-condition predictions.jsonl and models)")


if __name__ == "__main__":
    main()
