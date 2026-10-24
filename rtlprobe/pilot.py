"""Qualification, execution helpers, and evidence audits for a selected target."""

import argparse
import difflib
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from jsonschema import validate

from .evidence import (CODE_ROOT, ROOT, Runner, environment, filehash, identity, load, manifest,
                       save, treehashes, verify_manifest, workspace_lock)
from .mutation import apply, locate, locate_constant, safe_path
from .oracle import classify, historical_checker
from . import target

CONFIG = target.selected()
DESIGN = target.design_directory(target.configuration(CONFIG)) if CONFIG else None
REGISTRY = CODE_ROOT/"rtlprobe/operators.json"


def schema(value, name):
    if value.get("schema_version") == "pilot-2":
        name += "_v2"
    validate(value, load(CODE_ROOT/"rtlprobe/schemas"/(name+".json")))


def inputs(config):
    vendor = ROOT/config["vendor"]
    revision = subprocess.check_output(["git", "-C", str(vendor), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(vendor), "status", "--porcelain"], text=True)
    if revision != config["revision"] or dirty.strip():
        raise ValueError("Upstream checkout must be clean and match the pinned revision")
    paths = config["rtl"] + [config["testbench"]] + config["collateral"]
    if config.get('backend') == 'verilator_uvm':
        # FuseSoC generators need the pinned project and vendored dependencies.
        # Unrelated symlink assets are omitted; none may be a selected source.
        tracked = subprocess.check_output(['git', '-C', str(vendor), 'ls-files', '-z']).decode().split('\0')
        paths = [p for p in tracked if p and not (vendor/p).is_symlink()]

    for path in paths:
        safe_path(path)
        if (vendor/path).is_symlink():
            raise ValueError("Symlink sources unsupported in this pilot")
    return {path: filehash(vendor/path) for path in paths}


def fingerprint(config):
    code = {str(p.relative_to(CODE_ROOT)): filehash(p) for p in sorted((CODE_ROOT/"rtlprobe").rglob("*"))
            if p.is_file() and p.suffix in {".py", ".json"}}
    adapter = target.checker_path(config)
    code[str(adapter.relative_to(CODE_ROOT))] = filehash(adapter)
    record = {"config": config, "files": inputs(config), "environment": environment(),
              "implementation": code, "lock_sha256": filehash(CODE_ROOT/"requirements-dataset.lock.txt")}
    from .backends.common import fingerprint as backend_fingerprint
    record['environment']['backend'] = config.get('backend', 'icarus')
    if config.get('backend', 'icarus') != 'icarus':
        record['environment']['execution_backend'] = backend_fingerprint(config)
    return {"sha256": identity(record), "inputs": record}


def snapshot(config, destination):
    destination.mkdir(parents=True, exist_ok=False)
    for path in inputs(config):
        dst = destination/path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/config["vendor"]/path, dst)
        if config.get('backend', 'icarus') != 'icarus':
            shutil.copymode(ROOT/config['vendor']/path, dst)


def compile_design(runner, config, name, source):
    from .backends import select
    return select(config).build(runner, config, name, source)


def simulate(runner, config, name, source, binary):
    from .backends import select
    return select(config).run(runner, config, name, source, binary)


def structure(runner, config, name, source):
    # Lint reports warnings without treating existing upstream warnings as errors.
    lint = runner.require(name+"_lint", ["verilator", "--lint-only", "-Wno-fatal", "--top-module",
                          config["top"], *config["rtl"]], source, config["limits"]["compile_seconds"])
    dest = runner.out/(name+"_structure")
    dest.mkdir()
    netlist = dest/"netlist.json"
    script = dest/"synth.ys"
    quoted = " ".join('"'+str(source/p)+'"' for p in config["rtl"])
    script.write_text(f'read_verilog {quoted}\nhierarchy -check -top {config["top"]}\nsynth -top {config["top"]}\ncheck -assert\nwrite_json "{netlist}"\n')
    synth = runner.require(name+"_synthesis", ["yosys", "-Q", "-T", "-s", script], source,
                           config["limits"]["synthesis_seconds"])
    return {"status": "pass", "lint_run": lint["id"], "synthesis_run": synth["id"],
            "netlist": str(netlist.relative_to(runner.out)), "netlist_sha256": filehash(netlist),
            "source_mapping": "not_qualified", "functional_equivalence": "not_checked"}


def new_output(kind, tag, config=None):
    config = config or target.configuration(CONFIG)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = ROOT/"outputs"/config["target_id"]/kind/(tag+"-"+stamp)
    path.mkdir(parents=True, exist_ok=False)
    return path


def qualify():
    config = target.configuration(CONFIG)
    if config.get('backend', 'icarus') != 'icarus':
        from .backends.proof import qualify_original
        return qualify_original(config)
    fp = fingerprint(config)
    out = new_output("qualification", fp["sha256"][:12], config)
    runner = Runner(out, config["limits"])
    save(out/"fingerprint.json", fp)
    golden = out/"original"
    snapshot(config, golden)
    baseline = simulate(runner, config, "original", golden, compile_design(runner, config, "original", golden))
    if baseline["outcome"] != "pass":
        raise RuntimeError(f"Original failed qualification: {out}")
    structural = structure(runner, config, "original", golden)
    control = out/"control"
    shutil.copytree(golden, control)
    spec = config["control"]
    operator = next((o for o in load(REGISTRY)["operators"] if
                     {"id": o["id"], "version": o["version"]} == spec["operator"] and o["status"] == "approved"), None)
    if operator is None:
        raise ValueError("Control operator is not approved")
    data = (control/spec["path"]).read_bytes()
    if operator['id'] == 'literal_lsb_flip32':
        site = locate_constant(data, spec['line'], spec['lhs'], spec['statement'])
    else:
        site = locate(data, spec['line'], spec['lhs'], spec['rhs_tail'], spec['statement'])
    (control/spec["path"]).write_bytes(apply((control/spec["path"]).read_bytes(), site, operator))
    save(out/"negative_control.json", {"target": site, "path": spec["path"], "dataset_case": False})
    detected = simulate(runner, config, "control", control, compile_design(runner, config, "control", control))
    if detected["outcome"] != "functional_fail":
        raise RuntimeError(f"Checker did not detect control: {out}")
    if fingerprint(config) != fp:
        raise ValueError("Qualification inputs changed during execution")
    record = {"schema_version": "pilot-1", "design_id": config["design_id"], "status": "qualified",
              "fingerprint": fp["sha256"], "evidence": str(out.relative_to(ROOT)),
              "configuration": config, "baseline": baseline, "negative_control": detected,
              "structure": structural, "scope": config["scope"],
              "tests": [{**config["test_metadata"], "id": config["test_id"]}]}
    schema(record, "design")
    save(out/"design.json", record)
    # Preserve the exact implementation behind this qualification fingerprint.
    for relative, expected in fp["inputs"]["implementation"].items():
        if filehash(CODE_ROOT/relative) != expected:
            raise ValueError("Implementation changed before qualification publication")
        destination = out/"controller"/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CODE_ROOT/relative, destination)
    shutil.copyfile(CODE_ROOT/"requirements-dataset.lock.txt", out/"controller/requirements-dataset.lock.txt")
    manifest(out)
    DESIGN.mkdir(parents=True, exist_ok=True)
    save(DESIGN/"design.json", record)
    write_dossier(record, runner.records)
    print(f"QUALIFIED {out}")


def qualified():
    target.configuration(CONFIG)  # Fail clearly when no target has been selected.
    if target.configuration(CONFIG).get('control', {}).get('pending'):
        raise ValueError('Original-only proof is not qualification: control and restored PASS remain pending')
    design = load(DESIGN/"design.json")
    schema(design, "design")
    config = target.configuration(CONFIG)
    fp = fingerprint(config)
    if design["fingerprint"] != fp["sha256"] or design["status"] != "qualified":
        raise ValueError("Stale/unqualified dossier: run qualify with current inputs")
    out = ROOT/design["evidence"]
    verify_manifest(out)
    if load(out/"design.json") != design:
        raise ValueError("Dossier does not match sealed qualification evidence")
    return design, config, fp


def gates(original, mutants, restored, same_sources):
    return {"original_pass": original["outcome"] == "pass",
            "three_consistent_mutant_failures": len(mutants) == 3 and all(m["outcome"] == "functional_fail" for m in mutants)
                and bool(mutants[0]["signature"]) and all(m["signature"] == mutants[0]["signature"] for m in mutants),
            "same_mutant_executable": len({m["executable_sha256"] for m in mutants}) == 1,
            "same_mutant_sources": len({identity(m["source_hashes"]) for m in mutants}) == 1,
            "restored_pass": restored["outcome"] == "pass", "restored_source_identity": same_sources}


def generate(proposal_path):
    # Legacy entry point now shares duplicate protection and durable recovery.
    from .batch import run
    return run(proposal_path, cap=1)


def audit(path):
    path = Path(path).resolve()
    verify_manifest(path)
    record = load(path/"case.json")
    schema(record, "case")
    config = load(path/"fingerprint.json")["inputs"]["config"]
    frozen_fp = load(path/"fingerprint.json")
    if identity(frozen_fp["inputs"]) != frozen_fp["sha256"] or record["fingerprint"] != frozen_fp["sha256"]:
        raise ValueError("Fingerprint record is inconsistent")
    original, buggy, restored = [path/p for p in ("rtl/original", "rtl/buggy", "rtl/restored")]
    if treehashes(original) != frozen_fp["inputs"]["files"]:
        raise ValueError("Original snapshot differs from pinned inputs")
    if record["original"] != load(path/"original.json") or record["restored"] != load(path/"restored.json"):
        raise ValueError("Case summary disagrees with saved outcomes")
    if len(record["mutants"]) != 3 or any(m != load(path/f"mutant_{i}.json") for i, m in enumerate(record["mutants"], 1)):
        raise ValueError("Case summary must contain exactly three saved mutant executions")
    checks = gates(record["original"], record["mutants"], record["restored"], treehashes(original) == treehashes(restored))
    qual = ROOT/record["qualification"]
    verify_manifest(qual)
    if load(qual/"design.json")["fingerprint"] != record["fingerprint"]:
        raise ValueError("Reused qualification fingerprint differs")
    checker_config, checker_root, checker_mode = historical_checker(
        config, qual/'controller', target.configuration(CONFIG) if CONFIG else None)
    recorded_roots = set()
    for label, source in [("original", original), ("restored", restored), ("mutant_1", buggy), ("mutant_2", buggy), ("mutant_3", buggy)]:
        run = load(path/"commands"/label/"run.json")
        actual = classify((path/run["stdout"]).read_text(), (path/run["stderr"]).read_text(), run["returncode"], run["timed_out"],
                          config=checker_config, controller_root=checker_root)
        saved = load(path/(label+".json"))
        if any(saved.get(k) != v for k, v in actual.items()) or saved["source_hashes"] != treehashes(source):
            raise ValueError("Saved outcomes or source hashes disagree with evidence")
        binary = path/("mutant.vvp" if label.startswith("mutant") else label+".vvp")
        if saved["executable_sha256"] != filehash(binary):
            raise ValueError("Executable identity mismatch")
        # Preserve recorded host paths after copying evidence to another data root.
        command = run["command"]
        variant = "buggy" if label.startswith("mutant") else label
        if (len(command) != 3 or command[:2] != ["vvp", "-N"]
                or not Path(command[2]).is_absolute()
                or Path(command[2]).name != binary.name
                or run["cwd"] != str(Path(command[2]).parent/"rtl"/variant)):
            raise ValueError("Simulation command does not match recorded variant/executable")
        recorded_roots.add(Path(command[2]).parent)
    if len(recorded_roots) != 1:
        raise ValueError("Simulation commands reference inconsistent recorded case roots")
    if not all(checks.values()) or not all(record["checks"].values()):
        raise ValueError("Automated validation failed")
    changed_path = record["proposal"]["path"]
    operator = next(o for o in load(REGISTRY)["operators"] if {"id": o["id"], "version": o["version"]} == record["proposal"]["operator"])
    if apply((original/changed_path).read_bytes(), record["proposal"]["target"], operator) != (buggy/changed_path).read_bytes():
        raise ValueError("Patch proposal does not reconstruct buggy source")
    if [p for p, h in treehashes(original).items() if treehashes(buggy).get(p) != h] != [changed_path]:
        raise ValueError("Unexpected file changes, including possible checker changes")
    expected_patch = "".join(difflib.unified_diff((original/changed_path).read_text().splitlines(True),
        (buggy/changed_path).read_text().splitlines(True), fromfile="a/"+changed_path, tofile="b/"+changed_path))
    if (path/"mutation.patch").read_text() != expected_patch:
        raise ValueError("Saved patch does not match source variants")
    for variant, bundle in (("original", qual), ("buggy", path)):
        structural = record["structural"][variant]
        if structural["status"] != "pass" or filehash(bundle/structural["netlist"]) != structural["netlist_sha256"]:
            raise ValueError("Required structural evidence is absent or changed")
        for command in (structural["lint_run"], structural["synthesis_run"]):
            execution = load(bundle/"commands"/command/"run.json")
            if execution["returncode"] != 0 or execution["timed_out"]:
                raise ValueError("Required structural command did not pass")
    print(__import__("json").dumps({"audit_scope": "metadata_and_saved_execution_evidence", "result": "pass",
                                  "case_id": record["case_id"], "human_review": "pending", "fresh_simulations": 0,
                                  "checker_mode": checker_mode}, indent=2))


def write_dossier(record, commands):
    cfg = record["configuration"]
    text = [f"# Qualified {cfg['design_id']}", "",
            f"Status: **qualified** for `{record['scope']}`. Revision: `{cfg['revision']}`.", "",
            f"Repository: {cfg['repository_url']}. RTL top: `{cfg['top']}`. Existing TB: `{cfg['testbench']}`.", "",
            f"Authoritative record: design.json. Evidence: `{record['evidence']}`. Fingerprint: `{record['fingerprint']}`.", "",
            cfg.get('dossier_notes', 'See configuration, source collateral, and saved checker evidence for target scope.'), "",
            f"Existing checker: {cfg['test_metadata']['checker']}. Checkpoints: {', '.join(cfg['test_metadata']['checkpoints'])}.", "",
            "Observed original PASS and a detected separate AST-checked negative control. The control is not a dataset case. "
            "Baseline Verilator lint and Yosys synth/check passed; warnings are retained. These checks do not establish functional equivalence.", "",
            f"Coverage: {cfg.get('coverage', {'status': 'unavailable'})}. No unmeasured coverage is claimed.", "",
            f"Measured qualification command wall time: {sum(c['elapsed_seconds'] for c in commands):.3f} seconds. "
            "This excludes download, planning, parser setup, and human review.", "",
            "Reproduce with `scripts/rtlprobe.py --data-root DATA_ROOT --target-config TARGET_JSON qualify`. "
            "Baseline reuse requires the exact fingerprint and intact manifest. New environments require qualification.", ""]
    (DESIGN/'REPO.md').write_text('\n'.join(text))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="mode", required=True)
    subs.add_parser("qualify")
    gen = subs.add_parser("generate")
    gen.add_argument("proposal")
    aud = subs.add_parser("audit")
    aud.add_argument("case")
    args = parser.parse_args()
    if args.mode == "qualify":
        with workspace_lock():
            qualify()
    elif args.mode == "generate": generate(args.proposal)
    else: audit(args.case)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
