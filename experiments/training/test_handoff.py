"""
Handoff checks from Simul's README, section 6, on a scratch copy of the
package (the real package is never modified):

1. the real package passes; C0 and C4 give 7,180 rows and 20 positives with
   identical candidate-key order
2. one changed evidence byte makes validation fail
3. an invalid label join makes validation fail
4. feature output is byte-identical when supervision/ is absent
5. no label field appears in feature rows; every sample stays development_only

    python test_handoff.py PACKAGE_PATH SCRATCH_DIR [EMBEDDING_CACHE_DIR]
"""

import json
import shutil
import sys
from pathlib import Path

import embed
import features
import loader
from run_baseline import DEFAULT_EMB_CACHE, features_digest


def expect_fail(root, what):
    try:
        loader.validate_package(root)
    except loader.PackageError as e:
        print(f"  ok   {what} -> refused ({e})")
        return
    raise AssertionError(f"{what} was NOT detected")


def main(pkg_path, scratch, emb_cache=DEFAULT_EMB_CACHE):
    pkg_path, scratch = Path(pkg_path), Path(scratch)
    enc = embed.FrozenEncoder(emb_cache)

    print("1. real package")
    pkg = loader.EvidencePackage(pkg_path)
    labels, _ = loader.load_labels(pkg_path)
    keys = {}
    for cond in ("C0", "C4"):
        rows = []
        for sid in pkg.sample_ids:
            rows += features.build(pkg.view(sid, cond), enc, cond)[0]
        keys[cond] = [(r["sample_id"], r["candidate_id"]) for r in rows]
        pos = sum(cid in labels[s] for s, cid in keys[cond])
        assert len(rows) == 7180 and pos == 20, (cond, len(rows), pos)
        bad = [r for r in rows if {"label", "y", "positive_candidate_ids", "locations"} & set(r)]
        assert not bad, "label field inside feature rows"
        print(f"  ok   {cond}: {len(rows)} rows, {pos} positives, no label fields in features")
    assert keys["C0"] == keys["C4"]
    print("  ok   C0 and C4 candidate keys identical and in the same order")
    groups = loader.load_groups(pkg_path)
    assert all(g["split"] == "development_only" and not g["final_test_eligible"] for g in groups.values())
    print("  ok   all samples development_only")

    def fresh_copy(name):
        dst = scratch / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(pkg_path, dst)
        return dst

    print("2. changed evidence byte")
    c = fresh_copy("tamper_evidence")
    sample = sorted((c / "evidence").iterdir())[0]
    f = next((sample / "C0" / "rtl").rglob("*.v"))
    data = bytearray(f.read_bytes())
    data[200] = ord("X") if data[200] != ord("X") else ord("Y")
    f.write_bytes(bytes(data))
    expect_fail(c, "one byte changed in buggy RTL")

    print("3. invalid label join")
    c = fresh_copy("tamper_labels")
    lp = c / "supervision" / "labels.jsonl"
    rows = [json.loads(l) for l in lp.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows[0]["locations"][0]["line_1based"] += 1
    lp.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    integ = json.loads((c / "integrity.json").read_text(encoding="utf-8"))
    import hashlib
    integ["files"]["supervision/labels.jsonl"] = hashlib.sha256(lp.read_bytes()).hexdigest()
    (c / "integrity.json").write_text(json.dumps(integ), encoding="utf-8")   # hide the edit from the hash check
    expect_fail(c, "label moved to another line (hashes re-sealed)")

    print("4. features without supervision/")
    c = fresh_copy("no_supervision")
    shutil.rmtree(c / "supervision")
    shutil.rmtree(c / "provenance")
    blind = loader.EvidencePackage(c, validate=False)
    for cond in ("C0", "C4"):
        a, b = [], []
        for sid in pkg.sample_ids:
            a += features.build(pkg.view(sid, cond), enc, cond)[0]
            b += features.build(blind.view(sid, cond), enc, cond)[0]
        assert features_digest(a) == features_digest(b), cond
        print(f"  ok   {cond}: identical feature digest with labels/provenance removed")

    for name in ("tamper_evidence", "tamper_labels", "no_supervision"):
        shutil.rmtree(scratch / name)
    print("\nall handoff checks passed")


if __name__ == "__main__":
    main(*sys.argv[1:4])
