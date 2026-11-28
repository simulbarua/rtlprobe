"""Human-readable summaries of a run.json (Markdown report and console table)."""

LABEL_TEXT = {
    "in_sample_smoke_test": ("IN-SAMPLE SMOKE TEST. Models were trained and scored on the SAME cases. "
                             "These numbers check that the pipeline runs end to end; they are not "
                             "validation or test performance and must not be reported as such."),
    "held_out_test": "Held-out evaluation on the frozen split manifest named below.",
}
METRICS = ("top1", "top5", "top10", "mrr", "median_rank")


def _rows(part):
    for name, s in part["references"].items():
        yield f"reference: {name}", s, None
    for name, v in part["models"].items():
        yield name, v["mean"], v["sd"]


def _cell(mean, sd, k):
    fmt = "{:.3f}" if k == "mrr" else ("{:.1f}" if k == "median_rank" else "{:.2f}")
    return fmt.format(mean[k]) + (f" ± {fmt.format(sd[k])}" if sd else "")


def markdown(run):
    split = run["split"]
    lines = [f"# RTLProbe baseline training report: `{run['result_label']}`", "",
             f"> {LABEL_TEXT.get(run['result_label'], run['result_label'])}", "",
             "## Run", "",
             f"- Package check: {run['package_check']['status']}, {run['package_check']['cases']} cases, "
             f"{run['package_check']['candidate_rows_per_condition']} candidate rows per condition",
             f"- Mode: `{split['mode']}`; train {len(split['train'])} cases, validation {len(split['validation'])}, "
             f"test {len(split['test'])}" + (f"; split manifest `{split.get('split_id')}`" if split["mode"] == "held-out" else ""),
             f"- Feature version: `{run['feature_version']}`; encoder `{run['encoder']['model']}` @ `{run['encoder']['revision'][:12]}`",
             f"- Models: {', '.join(run['models'])}; seeds {run['seeds']}; model_config.json sha256 `{run['model_config_sha256'][:12]}`",
             f"- Python {run['python']} on {run['platform']}; {run['seconds']} s", "",
             "Metrics are per defect: Top-k = share of defects whose bug line ranks in the top k; "
             "MRR = mean reciprocal rank; ties share their average rank. Models show mean ± sd over seeds.", ""]
    for cond, res in run["conditions"].items():
        for p, part in res["partitions"].items():
            lines += [f"## {cond}: {p} ({res['rows'][p]} candidate rows, {len(res['features'])} features)", "",
                      "| Method | Top-1 | Top-5 | Top-10 | MRR | Median rank |", "|---|---|---|---|---|---|"]
            for name, mean, sd in _rows(part):
                lines.append(f"| {name} | " + " | ".join(_cell(mean, sd, k) for k in METRICS) + " |")
            lines.append("")
    lines += ["## Notes", "",
              "- Per-candidate scores with file, line and rank are in each condition's `predictions.jsonl`.",
              "- Per-case ranks for every seed are in `run.json`.",
              "- See LIMITATIONS.md in the training folder for known limits.", ""]
    return "\n".join(lines)


def console_table(run):
    out = [f"\n=== {run['result_label']} ==="]
    if run["result_label"] == "in_sample_smoke_test":
        out.append("(trained and scored on the SAME cases: pipeline check only)")
    out.append(f"{'cond':<5} {'part':<10} {'method':<32} {'top-1':>6} {'top-5':>6} {'top-10':>7} {'MRR':>6} {'median':>7}")
    for cond, res in run["conditions"].items():
        for p, part in res["partitions"].items():
            for name, s, _ in _rows(part):
                out.append(f"{cond:<5} {p:<10} {name:<32} {s['top1']:>6.2f} {s['top5']:>6.2f} {s['top10']:>7.2f} "
                           f"{s['mrr']:>6.3f} {s['median_rank']:>7.1f}")
    return "\n".join(out)
