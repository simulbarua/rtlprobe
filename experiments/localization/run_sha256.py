"""One isolated replay of a saved SHA-256 case, followed by blind baselines.

Target-specific observational instrumentation; does not admit new dataset cases.
Uses the existing upstream TB/checker and approved mutation mapper.
"""
import argparse
import difflib
from importlib.metadata import version
import json
from pathlib import Path
import re
import shutil
import sys
import time

CODE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CODE))
from rtlprobe.evidence import (Runner, environment, filehash, load, manifest, save,
                               treehashes, verify_manifest)
from rtlprobe.mutation import apply
from rtlprobe.oracle import classify
from vcdvcd import VCDVCD
from baseline import evaluate, extract


def parse_anchor(log):
    match = re.search(r"RTLPROBE_ANCHOR tc=1 time_units=(\S+) expected=([0-9a-f]+) actual=([0-9a-fxz]+)", log)
    if not match or match[2] == match[3]:
        raise ValueError("First comparison is not an observed failing anchor")
    return {"checkpoint": "tc1", "time_units": float(match[1]), "expected": match[2],
            "actual": match[3], "signal": "tb_sha256_core.dut.digest"}


def trace_evidence(path, anchor, graph):
    trace = VCDVCD(str(path))
    tick_seconds = float(trace.timescale["timescale"])
    seconds = anchor["time_units"] * 10 ** anchor["tb_time_unit_exponent"]
    end = round(seconds / tick_seconds)
    if abs(end * tick_seconds - seconds) > tick_seconds / 2:
        raise ValueError("Timestamp does not align with VCD resolution")
    references = {}
    for ref in trace.signals:
        normalized = re.sub(r"\[\d+(?::\d+)?\]$", "", ref)
        if normalized in references:
            raise ValueError("Ambiguous normalized VCD identity")
        references[normalized] = ref
    relevant = set(graph["dependencies"])
    relevant.update(s for values in graph["dependencies"].values() for s in values)
    relevant.update({"tb_sha256_core.dut.clk", "tb_sha256_core.dut.reset_n"})
    signals = {}
    for signal in sorted(relevant & references.keys()):
        events = [(t, value) for t, value in trace[references[signal]].tv if t <= end]
        if events:
            signals[signal] = {
                "vcd_reference": references[signal], "changes": len(events) - 1,
                "last_time_tick": events[-1][0], "value_at_anchor": events[-1][1],
                "events": events,
            }
    digest = signals[anchor["signal"]]["value_at_anchor"]
    if re.search("[xz]", digest) or int(digest, 2) != int(anchor["actual"], 16):
        raise ValueError("Timestamped checker observation disagrees with VCD")
    if trace.endtime < end:
        raise ValueError("Trace stops before failure")
    return {
        "timescale": str(trace.timescale["magnitude"]) + trace.timescale["unit"],
        "tick_seconds": tick_seconds, "window_start_tick": 0, "window_end_tick": end,
        "capture_start_tick": trace.begintime, "capture_end_tick": trace.endtime,
        "signal_count_in_capture": len(trace.signals), "signals": signals,
        "missing_graph_signals": sorted(relevant - references.keys()),
        "history": "full simulation from time zero; extracted through first checker failure",
        "limitations": ["VCD settled values do not preserve all delta-cycle ordering",
                        "some memories and constants may not be dumped",
                        "activity is not correctness evidence"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    case, out = args.case.resolve(), args.out.resolve()
    verify_manifest(case)
    before = treehashes(case)
    cfg = load(CODE / "targets/sha256/config.json")
    saved_cfg = load(case / "fingerprint.json")["inputs"]["config"]
    for key in ("repository_url", "revision", "top", "test_top", "rtl", "testbench",
                "compile_flags", "seed"):
        if cfg[key] != saved_cfg[key]:
            raise ValueError(f"Replay target mismatch: {key}")
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    runner = Runner(out, cfg["limits"])
    env = environment()
    env["packages"]["vcdvcd"] = version("vcdvcd")
    save(out / "environment.json", env)
    # Curator state never crosses the inference export boundary.
    record = load(case / "case.json")
    save(out / "curator/source.json", {
        "case_path": str(case), "manifest_sha256": filehash(case / "manifest.json"),
        "repository_url": cfg["repository_url"], "revision": cfg["revision"],
        "config": cfg,
    })
    save(out / "curator/label.json", {"path": record["ground_truth"]["path"],
                                      "line": record["ground_truth"]["line_1based"]})
    original, buggy, restored = (out / "replay" / name for name in ("original", "buggy", "restored"))
    shutil.copytree(case / "rtl/original", original)
    shutil.copytree(original, buggy)
    proposal = record["proposal"]
    operator = next(o for o in load(CODE / "rtlprobe/operators.json")["operators"]
                    if o["id"] == proposal["operator"]["id"] and o["version"] == proposal["operator"]["version"])
    source = buggy / proposal["path"]
    source.write_bytes(apply(source.read_bytes(), proposal["target"], operator))
    if treehashes(buggy) != treehashes(case / "rtl/buggy"):
        raise ValueError("Reconstructed mutant differs from saved case")
    outcomes = {}

    def compile_run(name, folder, binary=None, extra=()):
        if binary is None:
            binary = out / (name + ".vvp")
            runner.require(name + "_compile", ["iverilog", *cfg["compile_flags"], "-s", cfg["test_top"],
                           "-o", binary, *extra, *cfg["rtl"], cfg["testbench"]], folder, 60)
        execution = runner.run(name, ["vvp", "-N", binary], folder, 15)
        log = (out / execution["stdout"]).read_text()
        # Instrumentation messages are additive observations, not checker events.
        semantic_log = "\n".join(line for line in log.splitlines()
                                 if not line.startswith(("RTLPROBE_ANCHOR ", "VCD info:")))
        outcome = classify(semantic_log, (out / execution["stderr"]).read_text(),
                           execution["returncode"], execution["timed_out"], config=cfg)
        save(out / "outcomes" / (name + ".json"), outcome)
        outcomes[name] = outcome
        return binary, log

    compile_run("original", original)
    binary, failing_log = compile_run("failure_1", buggy)
    compile_run("failure_2", buggy, binary)
    compile_run("failure_3", buggy, binary)
    shutil.copytree(buggy, restored)
    runner.require("restore_patch", ["patch", "--batch", "--fuzz=0", "-R", "-p1",
                                   "-i", case / "mutation.patch"], restored, 15)
    if treehashes(restored) != treehashes(original):
        raise ValueError("Restoration changed source identity")
    compile_run("restored", restored)
    if outcomes["original"]["outcome"] != "pass" or outcomes["restored"]["outcome"] != "pass":
        raise ValueError("Baseline/restoration did not pass")
    signatures = [outcomes[f"failure_{i}"]["signature"] for i in (1, 2, 3)]
    if not signatures[0] or any(s != signatures[0] for s in signatures):
        raise ValueError("Functional failure is not reproducible")

    # Add only observation statements at an existing comparison; stimulus/checks unchanged.
    instrumented = out / "replay/instrumented"
    shutil.copytree(buggy, instrumented)
    tb = instrumented / cfg["testbench"]
    text = tb.read_text()
    needle = "\n     if (tb_digest == expected)"
    if text.count(needle) != 1:
        raise ValueError("Unrecognized pinned testbench instrumentation site/timescale")
    observed = text.replace(needle,
        '\n     $display("RTLPROBE_ANCHOR tc=%0d time_units=%0.3f expected=%064x actual=%064x", '
        'tc_number, $realtime, expected, tb_digest);\n' + needle)
    tb.write_text(observed)
    (out / "instrumentation.patch").write_text("".join(difflib.unified_diff(
        text.splitlines(True), observed.splitlines(True), fromfile=cfg["testbench"], tofile=cfg["testbench"])))
    monitor = instrumented / "trace_monitor.v"
    monitor.write_text('module trace_monitor;\ninitial begin\n'
                       '  $dumpfile("capture.vcd");\n'
                       '  $dumpvars(0, tb_sha256_core.dut);\n'
                       'end\nendmodule\n')
    traced_binary, traced_log = compile_run("trace", instrumented, extra=("-s", "trace_monitor", str(monitor)))
    if outcomes["trace"] != outcomes["failure_1"]:
        raise ValueError("Instrumentation changed checker verdict/signature")
    anchor = parse_anchor(traced_log)
    compiled_scale = re.search(r'\.scope module, "tb_sha256_core"[^\n]*\n\s*\.timescale (-?\d+) (-?\d+);',
                               traced_binary.read_text())
    if not compiled_scale:
        raise ValueError("Cannot establish actual testbench time unit")
    anchor.update(tb_time_unit_exponent=int(compiled_scale[1]),
                  tb_time_precision_exponent=int(compiled_scale[2]),
                  time_unit_provenance="Icarus compiled VVP scope; upstream has no timescale directive",
                  physical_time_interpretation="unspecified by upstream; do not infer nanoseconds")
    save(out / "anchor.json", anchor)
    sources = {p: (buggy / p).read_text() for p in cfg["rtl"]}
    extract_start = time.monotonic()
    graph = extract(sources, cfg["top"], cfg["test_top"] + ".dut")
    graph_seconds = time.monotonic() - extract_start
    save(out / "structure.json", graph)
    trace_start = time.monotonic()
    trace = trace_evidence(instrumented / "capture.vcd", anchor, graph)
    trace_seconds = time.monotonic() - trace_start
    save(out / "trace.json", trace)
    # Candidate segmentation uses syntax in all variants; only B/C get dependencies.
    candidates = [{k: c[k] for k in ("path", "line", "module", "instance", "kind", "lhs", "text")}
                  for c in graph["candidates"]]
    failure_text = ("tc1 digest mismatch\nExpected: " + anchor["expected"] + "\nGot: " + anchor["actual"])
    metrics, inputs = {}, {}
    for mode in ("rtl_logs", "rtl_logs_structure", "rtl_logs_structure_checker_trace"):
        payload = {"schema_version": "localization-pilot-1", "mode": mode,
                   "sources": sources, "failure_log": failure_text, "candidates": candidates}
        if mode != "rtl_logs":
            payload.update(structure=graph, anchor=anchor["signal"])
        if mode.endswith("checker_trace"):
            payload.update(checker_source={cfg["testbench"]: text}, trace=trace)
        input_path = out / "inference" / (mode + ".json")
        output_path = out / "predictions" / (mode + ".json")
        save(input_path, payload)
        output_path.parent.mkdir(exist_ok=True)
        # A fresh process receives only a neutral input filename and an output filename.
        runner.require("rank_" + mode, [sys.executable, Path(__file__).with_name("baseline.py"),
                                       input_path, output_path], out / "inference", 60)
        inputs[mode] = {"path": str(input_path.relative_to(out)), "sha256": filehash(input_path),
                        "bytes": input_path.stat().st_size}
    # Load ground truth for evaluation only after every prediction is on disk.
    label = load(out / "curator/label.json")
    for mode in inputs:
        metrics[mode] = evaluate(load(out / "predictions" / (mode + ".json")), label)
    # Automated hygiene check plus a precise export inventory; not an OS security sandbox.
    forbidden = [record["case_id"], proposal["proposal_id"], "ground_truth", "mutation.patch",
                 "lineage_id", "rtl/original", "rtl/restored", '"before"', '"after"']
    violations = {mode: [s for s in forbidden if s in (out / info["path"]).read_text()]
                  for mode, info in inputs.items()}
    if any(violations.values()):
        raise ValueError("Forbidden metadata in inference export")
    save(out / "leakage-audit.json", {"inputs": inputs, "forbidden_metadata_matches": violations,
         "boundary": "rank process reads only explicit JSON; curator/original/patch are not exported",
         "limitations": ["separate process is not filesystem isolation",
                        "developer saw label; policies are exploratory, not preregistered/blinded",
                        "known public design permits external memorization if a model is later used"],
         "model_calls": 0})
    if treehashes(case) != before:
        raise ValueError("Historical case changed")
    summary = {
        "experiment": "one development example; deterministic heuristic baselines; no ML/model call",
        "replay": {name: value["outcome"] for name, value in outcomes.items()},
        "metrics": metrics, "input_files": inputs, "anchor": anchor,
        "evidence": {"trace_bytes": (instrumented / "capture.vcd").stat().st_size,
                     "captured_signals": trace["signal_count_in_capture"],
                     "mapped_signals": len(trace["signals"]),
                     "missing_signals": len(trace["missing_graph_signals"]),
                     "candidate_count_before_cone": len(candidates),
                     "timescale": trace["timescale"], "window_end_tick": trace["window_end_tick"]},
        "cost": {"elapsed_seconds_before_seal": time.monotonic() - started,
                 "command_wall_seconds": sum(c["elapsed_seconds"] for c in runner.records),
                 "command_cpu_seconds": sum(c["cpu_seconds"] for c in runner.records),
                 "structure_seconds": graph_seconds, "trace_extraction_seconds": trace_seconds,
                 "model_calls": 0, "model_tokens": 0, "model_api_cost": 0},
        "limitations": graph["limitations"] + trace["limitations"] + [
            "one known development case, no held-out estimate",
            "no learned model and no golden trace comparison",
            "source-line labels; declarations/control conditions not independent candidates",
            "checker source is available but heuristic uses only its anchor",
            "rank activity is signal activity, not statement execution coverage"],
    }
    save(out / "summary.json", summary)
    implementation = out / "implementation"
    implementation.mkdir()
    for script in Path(__file__).parent.glob("*.py"):
        shutil.copyfile(script, implementation / script.name)
    for relative in ("rtlprobe/evidence.py", "rtlprobe/mutation.py", "rtlprobe/oracle.py",
                     "rtlprobe/target.py", "rtlprobe/operators.json",
                     "targets/sha256/checker.py", "targets/sha256/config.json",
                     "requirements-dataset.lock.txt"):
        destination = implementation / "core" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CODE / relative, destination)
    manifest(out)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
