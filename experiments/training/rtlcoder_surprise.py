"""
No-training reference ranking: RTLCoder token surprise.

A pretrained Verilog language model (RTLCoder) reads each buggy RTL file from
the top. For every token t_i it gives the probability of that token given all
earlier tokens; the token's surprise is

    s_i = -log p(t_i | t_1 .. t_{i-1})

A candidate line's score is the worst (largest) surprise among its tokens
(the line average is also saved). Lines the model finds most unexpected rank
first. Nothing is trained or tuned on the package: this is a fixed reference
ranking next to the trained baselines, not one of them.

Fixed settings (do not change between compared runs):
  model      ishorn5/RTLCoder-Deepseek-v1.1 @ 0e2a613d4fff24c110ebf27d15151f20d480f8b6
  precision  8-bit weights (bitsandbytes), device_map="auto"; needs a CUDA GPU
  context    1,024-token windows that overlap by 256 tokens, BOS prepended
  tokens     each source line is tokenized separately (with its newline), so
             every token belongs to exactly one line; this tokenizer's offset
             mapping is unreliable
  score      max token surprise on the line (primary); mean saved as well

Caveat: the starter package is SHA-256 from a public repository that may be in
RTLCoder's pretraining data, so results on it may be optimistic.

    python rtlcoder_surprise.py --package PATH --out NEW_DIR [--samples ID ...] [--evaluate]
"""

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import torch

import evaluate
import loader

MODEL_ID = "ishorn5/RTLCoder-Deepseek-v1.1"
REVISION = "0e2a613d4fff24c110ebf27d15151f20d480f8b6"
WINDOW, OVERLAP = 1024, 256
IDENTITY = {"model": MODEL_ID, "revision": REVISION, "precision": "8bit-bitsandbytes",
            "window": WINDOW, "overlap": OVERLAP, "tokenization": "per-line", "score": "max_token_surprise"}


def load_model():
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    if not torch.cuda.is_available():
        sys.exit("RTLCoder is loaded in 8-bit and needs a CUDA GPU; none was found")
    tok = AutoTokenizer.from_pretrained(MODEL_ID, revision=REVISION)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, revision=REVISION, device_map="auto",
                                                 quantization_config=BitsAndBytesConfig(load_in_8bit=True))
    model.eval()
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    return tok, model


def line_surprise(lines, cand_idx, tok, model, win=WINDOW, ctx=OVERLAP):
    """(mean, max) token surprise of each 0-based line index in cand_idx,
    each token predicted from everything before it in the file (within the
    sliding window)."""
    ids, line_of = [], []
    for k, line in enumerate(lines):
        piece = tok(line + "\n", add_special_tokens=False)["input_ids"]
        ids.extend(piece)
        line_of.extend([k] * len(piece))
    line_of = np.array(line_of)
    bos = tok.bos_token_id
    loss = np.full(len(ids), np.nan)
    start = 0
    while start < len(ids):
        lo, hi = max(0, start - ctx), min(len(ids), start + win - ctx)
        chunk = ([bos] if bos is not None else []) + ids[lo:hi]
        x = torch.tensor([chunk], device=model.device)
        with torch.no_grad():
            logp = torch.log_softmax(model(x).logits[0].float(), -1)
        nll = -logp[:-1].gather(1, x[0, 1:, None])[:, 0].cpu().numpy()
        shift = 1 if bos is not None else 0
        for t in range(start, hi):
            j = t - lo + shift          # position of token t in the chunk
            if j >= 1:
                loss[t] = nll[j - 1]    # predicted from position j - 1
        start = hi
    mean_s, max_s = [], []
    for k in cand_idx:
        sel = loss[line_of == k]
        sel = sel[~np.isnan(sel)]
        if len(sel) == 0:
            raise RuntimeError(f"no scored tokens for line {k + 1}")
        mean_s.append(float(sel.mean()))
        max_s.append(float(sel.max()))
    return np.array(mean_s), np.array(max_s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--samples", nargs="+", default=None, help="default: every sample in the package")
    ap.add_argument("--evaluate", action="store_true", help="also score against the package labels")
    a = ap.parse_args()

    out = Path(a.out)
    if out.exists():
        sys.exit(f"output directory exists, refusing to overwrite: {out}")
    t0 = time.time()
    pkg = loader.EvidencePackage(a.package)
    samples = a.samples or pkg.sample_ids
    unknown = set(samples) - set(pkg.sample_ids)
    if unknown:
        sys.exit(f"unknown samples: {sorted(unknown)[:3]}")
    tok, model = load_model()
    out.mkdir(parents=True)

    rows = []
    for sid in samples:
        view = pkg.view(sid, "C0")               # buggy RTL + candidates only; identical in every view
        cands = view.candidates
        mean_s, max_s = np.zeros(len(cands)), np.zeros(len(cands))
        for path in dict.fromkeys(c["path"] for c in cands):
            idx = [i for i, c in enumerate(cands) if c["path"] == path]
            m, x = line_surprise(view.source(path).splitlines(), [cands[i]["line"] - 1 for i in idx], tok, model)
            mean_s[idx], max_s[idx] = m, x
        ranks = evaluate.output_ranks(max_s, np.array([sid] * len(cands)))
        for c, m, x, r in zip(cands, mean_s, max_s, ranks):
            rows.append({"sample_id": sid, "candidate_id": c["candidate_id"], "path": c["path"], "line": c["line"],
                         "method": "rtlcoder_surprise", "score": float(x), "surprise_mean": float(m), "rank": int(r)})
        print(f"{sid}: {len(cands)} candidates scored")
    with open(out / "predictions.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    result = {"result_label": "no_training_reference", "method": IDENTITY, "samples": samples,
              "python": sys.version.split()[0], "platform": platform.platform(),
              "gpu": torch.cuda.get_device_name(0), "metrics": None}
    if a.evaluate:
        labels = loader.load_labels(a.package)[0]
        groups = loader.load_groups(a.package)
        sid = np.array([r["sample_id"] for r in rows])
        y = np.array([int(r["candidate_id"] in labels[r["sample_id"]]) for r in rows])
        sizes = [int(np.sum(sid == s)) for s in samples]
        cases = {k: evaluate.per_case(np.array([r[f] for r in rows]), sid, y)
                 for k, f in (("max", "score"), ("mean", "surprise_mean"))}
        result["metrics"] = {"surprise_max": evaluate.summarise(cases["max"]),
                             "surprise_mean": evaluate.summarise(cases["mean"]),
                             "random": evaluate.random_reference(sizes), "per_case_max": cases["max"]}
        result["development_only_cases"] = sum(groups[s]["split"] == "development_only" for s in samples)
        print(f"\n=== RTLCoder surprise, no training, {len(samples)} cases ===")
        print(f"{'method':<16} {'top-1':>6} {'top-5':>6} {'top-10':>7} {'MRR':>6} {'median':>7}")
        for k in ("surprise_max", "surprise_mean", "random"):
            s = result["metrics"][k]
            print(f"{k:<16} {s['top1']:>6.2f} {s['top5']:>6.2f} {s['top10']:>7.2f} {s['mrr']:>6.3f} {s['median_rank']:>7.1f}")
    result["seconds"] = round(time.time() - t0, 1)
    (out / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
