"""Experimental, conservative RTL dependencies and deterministic rankings.

No mutation, original RTL, case metadata, or evaluation-label inputs are accepted.
This is not a learned localizer or a bit-accurate temporal slice.
"""
import argparse
from collections import defaultdict, deque
import json
from pathlib import Path
import re
import tempfile
import time

from pyverilog.vparser.parser import VerilogParser



def walk(node):
    yield node
    for child in node.children():
        yield from walk(child)


def names(node):
    return {n.name for n in walk(node) if type(n).__name__ == "Identifier"}


def lhs_names(node):
    kind = type(node).__name__
    if kind in {"Lvalue", "Pointer", "Partselect"}:
        return lhs_names(node.var)
    if kind == "Identifier":
        return {node.name}
    if kind in {"LConcat", "Concat"}:
        return set().union(*(lhs_names(n) for n in node.children()))
    raise ValueError(f"Unsupported assignment LHS: {kind}")


def extract(sources, top, instance):
    """Overapproximate data/control dependencies, including sequential feedback.

    Arrays collapse to a single signal. Port connections use declared direction.
    Supports plain modules with named ports; rejects generate/functions/overrides.
    """
    from rtlprobe.candidates import extract_candidates
    syntax_inventory = extract_candidates(sources)
    if syntax_inventory['rejected']:
        raise ValueError('Candidate syntax rejected: ' + repr(syntax_inventory['rejected']))
    modules = {}
    for path, text in sorted(sources.items()):
        with tempfile.TemporaryDirectory(prefix="rtlprobe-localization-") as tmp:
            ast = VerilogParser(outputdir=tmp, debug=False).parse(text)
        for node in ast.description.definitions:
            if type(node).__name__ != "ModuleDef" or node.name in modules:
                raise ValueError("Expected unique plain modules")
            unsupported = {"GenerateStatement", "Function", "Task", "FunctionCall",
                           "TaskCall", "SystemCall"}
            if any(type(n).__name__ in unsupported for n in walk(node)):
                raise ValueError("Unsupported elaboration/function construct")
            modules[node.name] = (path, text, node)
    deps = defaultdict(set)
    candidates = []

    def visit_module(module, scope, ancestry=()):
        if module in ancestry or module not in modules:
            raise ValueError("Recursive or unknown module")
        path, text, node = modules[module]
        def visit(n, controls=frozenset(), sequential=False, bindings=None, block_scope=None):
            bindings = bindings or {}
            block_scope = block_scope or scope
            qualify = lambda ns: {bindings.get(name, scope + "." + name) for name in ns}
            def descend(child, child_controls=controls, child_sequential=sequential):
                visit(child, child_controls, child_sequential, bindings, block_scope)
            kind = type(n).__name__
            if kind == "Block" and n.scope:
                nested = block_scope + "." + n.scope
                local = dict(bindings)
                for stmt in n.statements:
                    if type(stmt).__name__ == "Decl":
                        for decl in stmt.list:
                            if hasattr(decl, "name"):
                                local[decl.name] = nested + "." + decl.name
                for stmt in n.statements:
                    visit(stmt, controls, sequential, local, nested)
                return
            if kind == "InstanceList":
                if n.parameterlist:
                    raise ValueError("Parameter overrides unsupported")
                for child in n.instances:
                    if child.array:
                        raise ValueError("Instance arrays unsupported")
                    child_scope = scope + "." + child.name
                    visit_module(child.module, child_scope, (*ancestry, module))
                    child_ast = modules[child.module][2]
                    directions = {d.name: type(d).__name__ for d in walk(child_ast)
                                  if type(d).__name__ in {"Input", "Output", "Inout"}}
                    for port in child.portlist:
                        if port.portname not in directions or port.argname is None:
                            raise ValueError("Only connected named ports supported")
                        formal = child_scope + "." + port.portname
                        actual = qualify(names(port.argname))
                        direction = directions[port.portname]
                        if direction == "Input":
                            deps[formal].update(actual)
                        elif direction == "Output":
                            for signal in qualify(lhs_names(port.argname)):
                                deps[signal].add(formal)
                        else:
                            raise ValueError("Inout ports unsupported")
                return
            if kind == "Always":
                edge_triggered = any(getattr(s, "type", None) in {"posedge", "negedge"}
                                     for s in n.sens_list.list)
                descend(n.statement, controls | names(n.sens_list) if edge_triggered else controls,
                        edge_triggered)
                return
            if kind == "IfStatement":
                for branch in (n.true_statement, n.false_statement):
                    if branch is not None:
                        descend(branch, controls | names(n.cond), sequential)
                return
            if kind in {"CaseStatement", "CasexStatement", "CasezStatement"}:
                for case in n.caselist:
                    condition = set().union(*(names(c) for c in (case.cond or ())))
                    descend(case.statement, controls | names(n.comp) | condition, sequential)
                return
            if kind == "ForStatement":
                descend(n.pre, controls, sequential)
                descend(n.post, controls | names(n.cond), sequential)
                descend(n.statement, controls | names(n.cond), sequential)
                return
            if kind in {"WhileStatement", "Repeat"}:
                raise ValueError("Loop dependency analysis unsupported")
            if kind in {"Assign", "BlockingSubstitution", "NonblockingSubstitution",
                        "Localparam", "Parameter"}:
                if kind in {"Localparam", "Parameter"}:
                    targets, inputs = {n.name}, names(n.value)
                else:
                    targets = lhs_names(n.left)
                    inputs = names(n.right) | (names(n.left) - targets)
                outputs = qualify(targets)
                incoming = qualify(inputs | set(controls))
                for signal in outputs:
                    deps[signal].update(incoming)
                candidates.append({
                    "path": path, "line": n.lineno, "module": module, "instance": scope,
                    "kind": kind, "lhs": sorted(outputs), "dependencies": sorted(incoming),
                    "sequential": sequential,
                    "text": text.splitlines()[n.lineno - 1].strip(),
                })
                return
            for child in n.children():
                descend(child)

        visit(node)
        # Candidate coverage comes from source syntax, independently of the
        # operator registry. Existing graph exclusions still raise above.
        for candidate in syntax_inventory['candidates']:
            if candidate['path'] == path and candidate['module'] == module:
                candidates.append({**candidate, 'instance': scope,
                    'lhs': [scope + '.' + n for n in candidate['lhs']],
                    'dependencies': [scope + '.' + n for n in candidate['dependencies']],
                    'sequential': False})

    visit_module(top, instance)
    # Evaluation uses source lines. Multiple assignments starting on one line
    # (e.g. a for-loop initializer/increment) must not inflate the shortlist.
    locations = {}
    for candidate in candidates:
        key = (candidate["path"], candidate["line"], candidate["instance"])
        if key not in locations:
            locations[key] = candidate
        else:
            old = locations[key]
            if candidate['kind'] == 'source_syntax':
                old['site_spans'] = candidate['site_spans']
                old['syntax_kinds'] = candidate['syntax_kinds']
                # Keep the graph extractor's scope-resolved names.
                continue
            old["lhs"] = sorted(set(old["lhs"]) | set(candidate["lhs"]))
            old["dependencies"] = sorted(set(old["dependencies"]) | set(candidate["dependencies"]))
            old["sequential"] |= candidate["sequential"]
            old["kind"] = "multiple_assignments_on_line"
    return {"candidates": list(locations.values()),
            "dependencies": {k: sorted(v) for k, v in sorted(deps.items())},
            "limitations": ["signal-level, not bit-level", "arrays collapsed",
                            "procedural for loops collapsed, not unrolled",
                            "branch feasibility not evaluated", "no cycle-accurate slicing",
                            "source syntax includes if/ternary conditions and binary expression sites"]}


def distances(graph, anchors):
    distance = {anchor: 0 for anchor in anchors}
    pending = deque(anchors)
    while pending:
        current = pending.popleft()
        for upstream in graph.get(current, []):
            if upstream not in distance:
                distance[upstream] = distance[current] + 1
                pending.append(upstream)
    return distance


def rank(payload):
    """Only consumes the exported allowlisted inference bundle."""
    allowed = {"schema_version", "mode", "sources", "failure_log", "candidates",
               "structure", "anchor", "checker_source", "trace"}
    if set(payload) - allowed:
        raise ValueError("Unexpected inference fields")
    mode = payload["mode"]
    if mode not in {"rtl_logs", "rtl_logs_structure", "rtl_logs_structure_checker_trace"}:
        raise ValueError("Unknown ablation")
    structural = mode != "rtl_logs"
    dynamic = mode.endswith("checker_trace")
    distance = distances(payload["structure"]["dependencies"], [payload["anchor"]]) if structural else {}
    terms = set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", payload["failure_log"]))
    results = []
    for c in payload["candidates"]:
        if structural and not any(s in distance for s in c["lhs"]):
            continue
        row = {**c}
        row["distance"] = min((distance[s] for s in c["lhs"] if s in distance), default=None)
        row["lexical_overlap"] = len(terms & set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", c["text"])))
        observations = []
        if dynamic:
            for signal in c["lhs"]:
                if signal in payload["trace"]["signals"]:
                    observations.append({"signal": signal, **payload["trace"]["signals"][signal]})
        row["observations"] = observations
        row["activity"] = max((o["changes"] for o in observations), default=0)
        row["hypothesis"] = (
            "This statement may contribute to the observed failure; dependency/activity "
            "does not establish that its behavior is incorrect."
        )
        row["confirmation_check"] = "Check this assignment and its enabling conditions against the intended behavior."
        results.append(row)
    # Each tie is reproducible; lexical order is arbitrary and is reported as such.
    def key(c):
        prefix = (c["distance"], -c["activity"] if dynamic else 0) if structural else (-c["lexical_overlap"],)
        return (*prefix, c["path"], c["line"], c["instance"], c["kind"])
    results.sort(key=key)
    return {"mode": mode, "candidate_count": len(results), "ranking": results,
            "policy": "backward distance, then activity for trace mode; lexical overlap for RTL/log mode; source-order ties",
            "score_is_probability": False,
            "trace_context": {k: payload["trace"][k] for k in
                              ("timescale", "window_start_tick", "window_end_tick",
                               "missing_graph_signals")} if dynamic else None}


def evaluate(result, label):
    hits = [i for i, c in enumerate(result["ranking"], 1)
            if c["path"] == label["path"] and c["line"] == label["line"]]
    position = min(hits) if hits else None
    return {"candidate_inclusion": bool(hits), "candidate_count": result["candidate_count"],
            "rank": position, "reciprocal_rank": 1 / position if position else 0,
            **{f"top_{k}": int(position is not None and position <= k) for k in (1, 5, 10)},
            "rank_fraction": position / result["candidate_count"] if position else None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    started = time.monotonic()
    result = rank(json.loads(args.input.read_text()))
    result["ranking_seconds"] = time.monotonic() - started
    args.output.write_text(json.dumps(result, indent=2) + "\n")
