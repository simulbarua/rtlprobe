"""
Schema-aware loader for an RTLProbe starter/dataset package.

Two strictly separate entry points:
  EvidencePackage  - evidence only (metadata/samples.jsonl + evidence views).
                     Everything a feature builder may see. Never opens
                     supervision/ or provenance/.
  load_labels      - supervision/labels.jsonl, used only by training and
                     evaluation, joined on (sample_id, candidate_id).

validate_package() re-checks integrity the same way the package's own
tools/check_package.py does (file hashes, per-view manifests, buggy-source
hashes, identical candidate universes across views, labels pointing at
existing candidates), so this pipeline refuses changed evidence or bad
label joins on its own.
"""

import hashlib
import json
from pathlib import Path, PurePosixPath

CONDITIONS = ("C0", "C1", "C2", "C3", "C4", "M")


class PackageError(ValueError):
    pass


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _rows(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _inside(root, rel):
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts or "\\" in rel:
        raise PackageError(f"unsafe relative path: {rel}")
    full = root.joinpath(*p.parts)
    if not full.resolve().is_relative_to(root.resolve()) or full.is_symlink():
        raise PackageError(f"path escapes package or is a symlink: {rel}")
    return full


def _require(ok, msg):
    if not ok:
        raise PackageError(msg)


class EvidenceView:
    """One sealed condition export (e.g. C4) of one sample. Read-only."""

    def __init__(self, folder, manifest):
        self.folder = folder
        self.manifest = manifest
        self.condition = manifest["condition"]
        self.sample_id = manifest["neutral_id"]
        self._cache = {}

    def has(self, rel):
        return rel in self.manifest["files"]

    def json(self, rel):
        if rel not in self._cache:
            _require(self.has(rel), f"{rel} is not part of {self.sample_id}/{self.condition}")
            self._cache[rel] = _json(_inside(self.folder, rel))
        return self._cache[rel]

    def jsonl(self, rel):
        _require(self.has(rel), f"{rel} is not part of {self.sample_id}/{self.condition}")
        return _rows(_inside(self.folder, rel))

    def source(self, path):
        """Exact buggy RTL bytes as text, by candidate path (e.g. src/rtl/x.v)."""
        return _inside(self.folder, "rtl/" + path).read_text(encoding="utf-8")

    @property
    def candidates(self):
        return self.json("candidates.json")["candidates"]


class EvidencePackage:
    """Evidence-only view of a package. Deliberately has no access to labels."""

    def __init__(self, root, validate=True):
        self.root = Path(root).resolve()
        if validate:
            self.summary = validate_package(self.root)
        self.samples = sorted(_rows(self.root / "metadata/samples.jsonl"), key=lambda s: s["sample_id"])
        self.sample_ids = [s["sample_id"] for s in self.samples]

    def view(self, sample_id, condition):
        s = next(x for x in self.samples if x["sample_id"] == sample_id)
        folder = _inside(self.root, s["conditions"][condition]["path"])
        return EvidenceView(folder, _json(folder / "manifest.json"))


def load_labels(root):
    """{sample_id: set(positive candidate ids)} plus raw rows. Training/eval only."""
    rows = _rows(Path(root) / "supervision/labels.jsonl")
    return {r["sample_id"]: set(r["positive_candidate_ids"]) for r in rows}, rows


def load_groups(root):
    return {r["sample_id"]: r for r in _rows(Path(root) / "supervision/groups.jsonl")}


def validate_package(root):
    root = Path(root).resolve()
    files = list(root.rglob("*"))
    _require(not any(p.is_symlink() for p in files), "symlinks are not permitted")
    integrity = _json(root / "integrity.json")
    actual = {p.relative_to(root).as_posix(): _sha(p) for p in files
              if p.is_file() and p != root / "integrity.json"}
    _require(actual == integrity["files"], "package files changed, missing, or unexpected")

    samples = _rows(root / "metadata/samples.jsonl")
    labels = {r["sample_id"]: r for r in _rows(root / "supervision/labels.jsonl")}
    groups = load_groups(root)
    ids = {s["sample_id"] for s in samples}
    _require(len(ids) == len(samples) == len(labels) == len(groups), "duplicate or missing samples")
    _require(ids == set(labels) == set(groups), "sample joins differ between metadata and supervision")

    total = 0
    for s in samples:
        sid = s["sample_id"]
        _require(set(s["conditions"]) == set(CONDITIONS), f"{sid}: missing evidence condition")
        manifests, inventories = {}, {}
        for cond, info in s["conditions"].items():
            folder = _inside(root, info["path"])
            _require(_sha(folder / "manifest.json") == info["manifest_sha256"], f"{sid}/{cond}: manifest hash")
            m = _json(folder / "manifest.json")
            _require(m["condition"] == cond and m["neutral_id"] == sid, f"{sid}/{cond}: wrong sample/condition")
            _require(m["ready"] and not m["missing"], f"{sid}/{cond}: incomplete export")
            observed = {p.relative_to(folder).as_posix(): _sha(p) for p in folder.rglob("*")
                        if p.is_file() and p != folder / "manifest.json"}
            _require(observed == m["files"], f"{sid}/{cond}: export contents differ from manifest")
            for name, h in m["source_hashes"].items():
                _require(_sha(_inside(folder, "rtl/" + name)) == h, f"{sid}/{cond}: buggy source hash")
            manifests[cond], inventories[cond] = m, _json(folder / "candidates.json")
        ref = inventories["C4"]
        for cond in CONDITIONS:
            _require(inventories[cond] == ref, f"{sid}: candidate universe differs in {cond}")
            for k in ("source_hashes", "buggy_snapshot_sha256", "candidate_inventory_id", "evidence_binding_sha256"):
                _require(manifests[cond][k] == manifests["C4"][k], f"{sid}: {k} differs in {cond}")
        cands = ref["candidates"]
        by_id = {c["candidate_id"]: c for c in cands}
        _require(len(by_id) == len(cands) == s["candidate_count"], f"{sid}: candidate count/duplicates")
        lab = labels[sid]
        _require(lab["candidate_inventory_id"] == ref["inventory_id"] == s["candidate_inventory_id"],
                 f"{sid}: label inventory mismatch")
        _require(lab["mapping_status"] == "mapped" and lab["positive_candidate_ids"], f"{sid}: unmapped label")
        expected = set()
        for loc in lab["locations"]:
            _require(manifests["C4"]["source_hashes"][loc["path"]] == loc["buggy_source_sha256"],
                     f"{sid}: label points at other source bytes")
            expected |= {c["candidate_id"] for c in cands if c["path"] == loc["path"] and c["line"] == loc["line_1based"]}
        _require(expected == set(lab["positive_candidate_ids"]) and expected <= set(by_id),
                 f"{sid}: label-to-candidate mapping mismatch")
        _require(groups[sid]["split"] == "development_only" or groups[sid].get("final_test_eligible"),
                 f"{sid}: unknown split status")
        total += len(cands)
    return {"status": "passed", "cases": len(samples), "views": len(samples) * len(CONDITIONS),
            "candidate_rows_per_condition": total}
