"""
Evidence-only feature builder, versioned. See FEATURES.md for definitions.

Input: one EvidenceView (one sample, one condition). Output: one row per
candidate keyed by (sample_id, candidate_id). This module never reads
supervision, provenance, line numbers as features, IDs, operator type, or
anything outside the selected view; every value derives from files listed in
that view's manifest. Missing evidence is NaN plus an availability flag,
never 0.
"""

import math
import re
from collections import defaultdict, deque

import numpy as np

from embed import cosine

FEATURE_VERSION = "rtlprobe-baseline-features-v2"   # v2: + graph_register_depth, graph_is_register

GROUPS = {
    "code_log": ["log_overlap", "anchor_resolved", "anchor_mention", "anchor_src_distance",
                 "emb_log_sim", "universe_size"],
    "structure": ["graph_mapped", "graph_back_dist", "graph_reachable", "graph_register_depth",
                  "graph_is_register", "graph_fanin", "graph_fanout", "module_dist"],
    "waveform": ["wave_available", "wave_changed", "wave_toggles_log1p", "wave_time_since_change",
                 "wave_has_xz"],
    "specification": ["spec_sim_max"],
}
CATEGORICAL = ["syntax_kind"]
CONDITION_GROUPS = {
    "C0": ["code_log"],
    "C1": ["code_log", "structure"],
    "C2": ["code_log", "waveform"],
    "C3": ["code_log", "specification"],
    "C4": ["code_log", "structure", "waveform", "specification"],
}

KEYWORDS = set("""module endmodule input output inout wire reg logic integer parameter localparam assign
always begin end if else case casez casex endcase default posedge negedge or and not for generate
endgenerate genvar function endfunction task endtask initial signed unsigned""".split())
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PORT = re.compile(r"\boutput\s+(?:wire|reg|logic)?\s*\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*([A-Za-z_]\w*)")


def numeric_feature_names(condition):
    return [f for g in CONDITION_GROUPS[condition] for f in GROUPS[g]]


def idents(text):
    return {t for t in IDENT.findall(text) if t not in KEYWORDS and len(t) > 1 and not t.isdigit()}


def failure_text(log):
    """Failure part of the checker log: from the first error line to the end."""
    lines = log.splitlines()
    first = next((i for i, l in enumerate(lines) if re.search(r"(?i)\berror\b|not successful", l)), None)
    part = lines[first:] if first is not None else lines[-40:]
    return "\n".join(part)


def resolve_anchor(view):
    """Anchor = top-module output port(s) whose bit width equals the width of
    the value the checker compared (hex digits x 4). Uses only the checker
    verdict and the buggy RTL, both present in every condition."""
    common, checker = view.json("common.json"), view.json("checker.json")
    top = common["configuration"]["top"]
    widths = {len(c["actual"]) * 4 for c in checker["verdict"].get("signature", [])
              if isinstance(c.get("actual"), str) and re.fullmatch(r"[0-9a-fA-F]+", c["actual"])}
    names = set()
    for path in common["configuration"]["rtl"]:
        src = view.source(path)
        m = re.search(rf"\bmodule\s+{top}\b", src)
        if not m:
            continue
        for a, b, name in PORT.findall(src[m.start():]):
            if abs(int(a) - int(b)) + 1 in widths:
                names.add(name)
    return sorted(names)


def context_text(view, cand, before=2, after=2, _cache={}):
    key = (id(view), cand["path"])
    if key not in _cache:
        _cache.clear()
        _cache[key] = view.source(cand["path"]).splitlines()
    lines = _cache[key]
    i = cand["line"] - 1
    return "\n".join(l.strip() for l in lines[max(0, i - before):i + after + 1])


def build(view, encoder, condition):
    groups = CONDITION_GROUPS[condition]
    cands = view.candidates
    n = len(cands)
    log = view.json("checker.json")["plain_buggy_log"]["stdout"]
    log_ids = idents(log)
    anchors = resolve_anchor(view)
    rows = [{"sample_id": view.sample_id, "candidate_id": c["candidate_id"], "condition": condition,
             "syntax_kind": (c["syntax_kinds"] or ["none"])[0]} for c in cands]

    # ---- code / log (all conditions)
    anchor_lines = defaultdict(list)
    if anchors:
        for path in {c["path"] for c in cands}:
            for ln, text in enumerate(view.source(path).splitlines(), 1):
                if idents(text) & set(anchors):
                    anchor_lines[path].append(ln)
    contexts = [context_text(view, c) for c in cands]
    emb_ctx = encoder.encode(contexts)
    emb_log = encoder.encode([failure_text(log)])
    log_sim = cosine(emb_ctx, emb_log)[:, 0]
    for r, c, s in zip(rows, cands, log_sim):
        ids = idents(c["text"]) | set(c.get("lhs") or [])
        r["log_overlap"] = len(ids & log_ids) / len(ids) if ids else math.nan
        r["anchor_resolved"] = float(bool(anchors))
        r["anchor_mention"] = float(bool(ids & set(anchors))) if anchors else math.nan
        lines = anchor_lines.get(c["path"], [])
        r["anchor_src_distance"] = float(min(abs(c["line"] - l) for l in lines)) if lines else math.nan
        r["emb_log_sim"] = float(s)
        r["universe_size"] = float(n)

    # ---- structure (C1, C4): graph + alignment
    if "structure" in groups:
        g, al = view.json("structure/graph.json"), view.json("structure/alignment.json")
        scope = g["context"]["dut_scope"]
        preds, succ = defaultdict(set), defaultdict(set)
        for e in g["edges"]:
            preds[e["target"]].add(e["source"])
            succ[e["source"]].add(e["target"])
        starts = [f"{scope}.{a}" for a in anchors]
        dist = {s: 0 for s in starts}
        q = deque(starts)
        while q:                                  # backward: from anchor towards its drivers
            u = q.popleft()
            for p in preds[u]:
                if p not in dist:
                    dist[p] = dist[u] + 1
                    q.append(p)
        mapping = {m["candidate_id"]: m for m in al["mappings"]}
        # registers: signals written by a non-blocking assignment (the LHS names of
        # such candidates, matched to that candidate's aligned signals)
        registers = set()
        for c in cands:
            m = mapping.get(c["candidate_id"])
            if m and m["status"] == "mapped" and "NonblockingAssignmentExpression" in c["syntax_kinds"]:
                lhs = set(c.get("lhs") or [])
                registers |= {s for s in m["signals"] if s.rsplit(".", 1)[-1] in lhs}
        # register depth: fewest registers entered on any backward path from the
        # anchor (0-1 breadth-first search; entering a register costs 1)
        depth = {s: 0 for s in starts}
        q = deque(starts)
        while q:
            u = q.popleft()
            for p in preds[u]:
                nd = depth[u] + (1 if p in registers else 0)
                if nd < depth.get(p, math.inf):
                    depth[p] = nd
                    (q.appendleft if nd == depth[u] else q.append)(p)
        for r, c in zip(rows, cands):
            m = mapping.get(c["candidate_id"])
            sigs = m["signals"] if m and m["status"] == "mapped" else []
            r["graph_mapped"] = float(bool(sigs))
            d = [dist[s] for s in sigs if s in dist]
            r["graph_reachable"] = float(bool(d)) if sigs and anchors else math.nan
            r["graph_back_dist"] = float(min(d)) if d else math.nan
            rd = [depth[s] for s in sigs if s in depth]
            r["graph_register_depth"] = float(min(rd)) if rd else math.nan
            r["graph_is_register"] = float(bool(set(sigs) & registers)) if sigs else math.nan
            r["graph_fanin"] = float(max(len(preds[s]) for s in sigs)) if sigs else math.nan
            r["graph_fanout"] = float(max(len(succ[s]) for s in sigs)) if sigs else math.nan
            inst = (m or {}).get("instance")
            if inst:
                a, b = inst.split("."), scope.split(".")
                k = 0
                while k < min(len(a), len(b)) and a[k] == b[k]:
                    k += 1
                r["module_dist"] = float((len(a) - k) + (len(b) - k))
            else:
                r["module_dist"] = math.nan

    # ---- waveform (C2, C4): buggy failure window; candidate -> signals by LHS names
    if "waveform" in groups:
        tr = view.json("waveform/trace.json")
        released = tr["reset"]["released_tick"] if tr["reset"]["status"] == "observed" else None
        win = next(w for w in tr["windows"] if w["window"]["kind"] == "reset_to_first_failure")
        end = win["window"]["end_tick"]
        by_local = defaultdict(list)
        for s in win["history"]["signals"]:
            for src in s["source_signals"]:
                by_local[src.rsplit(".", 1)[-1]].append(s)
        for r, c in zip(rows, cands):
            sigs = [s for name in (c.get("lhs") or []) for s in by_local.get(name, [])]
            if not sigs or released is None:
                for f in GROUPS["waveform"]:
                    r[f] = math.nan
                r["wave_available"] = 0.0
                continue
            toggles, last, xz = 0, None, False
            for s in sigs:
                prev = None
                for tick, val in s["events"]:
                    xz |= bool(re.search(r"[xXzZ]", val))
                    if tick > released and prev is not None and val != prev:
                        toggles += 1
                        last = tick if last is None else max(last, tick)
                    prev = val
            r["wave_available"] = 1.0
            r["wave_changed"] = float(toggles > 0)
            r["wave_toggles_log1p"] = math.log1p(toggles)
            span = max(1, end - released)
            r["wave_time_since_change"] = (end - last) / span if last is not None else math.nan
            r["wave_has_xz"] = float(xz)

    # ---- specification (C3, C4): nearest record in the full fixed store
    if "specification" in groups:
        reqs = view.jsonl("specification/requirements.jsonl")
        emb_req = encoder.encode([r["text"] for r in reqs])
        sims = cosine(emb_ctx, emb_req)
        for r, s in zip(rows, sims.max(axis=1)):
            r["spec_sim_max"] = float(s)

    for r in rows:
        for f in numeric_feature_names(condition):
            r.setdefault(f, math.nan)
    meta = {"feature_version": FEATURE_VERSION, "condition": condition, "anchors": anchors,
            "numeric_features": numeric_feature_names(condition), "categorical": CATEGORICAL}
    return rows, meta


def matrix(rows, condition):
    names = numeric_feature_names(condition)
    return np.array([[r[f] for f in names] for r in rows], dtype=float), names
