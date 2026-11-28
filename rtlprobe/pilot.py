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
                       save, treehashes, verify_manifest, workspace_lock, require_execution_guard,
                       begin_command, end_command)
from .mutation import apply, locate, locate_constant, locate_operator, revert, safe_path
from .oracle import classify, historical_checker
from . import target

CONFIG = target.selected()
DESIGN = target.design_directory(target.configuration(CONFIG)) if CONFIG else None
REGISTRY = CODE_ROOT/"rtlprobe/operators.json"
CURRENT_VALIDATION_POLICY = 'mutation-validation-v2'
LEGACY_VALIDATION_POLICY = 'mutation-validation-v1'


def validation_policy(record):
    policy = record.get('validation_policy', LEGACY_VALIDATION_POLICY)
    if policy not in (LEGACY_VALIDATION_POLICY, CURRENT_VALIDATION_POLICY):
        raise ValueError('Unknown mutation validation policy')
    return policy


def mutant_run_count(record):
    if validation_policy(record) == LEGACY_VALIDATION_POLICY:
        return 3
    prediction = record['proposal']['prediction']
    if 'third_run_reason' not in prediction:
        return 2
    reason = prediction['third_run_reason']
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
        raise ValueError('A requested third mutant run requires a specific reason')
    return 3


def validation_plan(config, proposal):
    if proposal['primary_test'] != config['test_id'] or proposal['fallback_tests']:
        raise ValueError('Mutation must use the qualified selected test')
    default_scope = 'test_specific' if len(config.get('admitted_tests', [])) > 1 else 'shared'
    test_scope = config.get('test_scope', default_scope)
    return {'original': 'fresh' if test_scope == 'test_specific' else 'reuse_qualification',
            'mutant_runs': mutant_run_count({'validation_policy': CURRENT_VALIDATION_POLICY, 'proposal': proposal})}


def repeatability_check(record):
    return 'two_consistent_mutant_failures' if mutant_run_count(record) == 2 else 'three_consistent_mutant_failures'


def matching_mutant_failures(record, mutants):
    return (len(mutants) == mutant_run_count(record) and bool(mutants[0]['signature'])
            and all(m['outcome'] == 'functional_fail' and m['signature'] == mutants[0]['signature'] for m in mutants))


def schema(value, name):
    if value.get("schema_version") == "pilot-2":
        name += "_v2"
    validate(value, load(CODE_ROOT/"rtlprobe/schemas"/(name+".json")))


def input_path(config, path):
    """Target-owned testbench files are bound separately from pinned upstream RTL."""
    if path == config['testbench'] and 'testbench_asset_sha256' in config:
        asset = CODE_ROOT / safe_path(path)
        if (not asset.resolve().is_relative_to(CODE_ROOT/'targets'/config['target_id'])
                or any(p.is_symlink() for p in (asset, *asset.parents))
                or filehash(asset) != config['testbench_asset_sha256']):
            raise ValueError('Invalid target-owned testbench or changed contents')
        return asset
    return ROOT/config['vendor']/path


def source_git_command(config, vendor, args):
    # Git status can refresh the index even when the checkout is clean.
    options = ['--no-optional-locks'] if config.get('target_id') == 'aes' and args[0] == 'status' else []
    return ['git', *options, '-C', str(vendor), *args]


def inputs(config, *, execution_guard=None):
    vendor = ROOT/config["vendor"]
    def query(args, **kwargs):
        command = source_git_command(config, vendor, args)
        name = 'source_revision' if args[0] == 'rev-parse' else 'source_status' if args[0] == 'status' else 'source_inventory'
        timeout = begin_command(execution_guard, name, command, None, 15)
        result = subprocess.check_output(command, timeout=timeout, **kwargs)
        end_command(execution_guard, {'id': name, 'returncode': 0, 'timed_out': False, 'interrupted': False})
        return result
    revision = query(['rev-parse', 'HEAD'], text=True).strip()
    dirty = query(['status', '--porcelain'], text=True)
    if revision != config["revision"] or dirty.strip():
        raise ValueError("Upstream checkout must be clean and match the pinned revision")
    paths = config["rtl"] + [config["testbench"]] + config["collateral"]
    if config.get('backend') == 'verilator_uvm':
        # FuseSoC generators need the pinned project and vendored dependencies.
        # Unrelated symlink assets are omitted; none may be a selected source.
        tracked = query(['ls-files', '-z']).decode().split('\0')
        paths = [p for p in tracked if p and not (vendor/p).is_symlink()]

    for path in paths:
        safe_path(path)
        if (vendor/path).is_symlink():
            raise ValueError("Symlink sources unsupported in this pilot")
    return {path: filehash(input_path(config, path)) for path in paths}


def fingerprint(config, *, execution_guard=None):
    code = {str(p.relative_to(CODE_ROOT)): filehash(p) for p in sorted((CODE_ROOT/"rtlprobe").rglob("*"))
            if p.is_file() and p.suffix in {".py", ".json"}}
    adapter = target.checker_path(config)
    code[str(adapter.relative_to(CODE_ROOT))] = filehash(adapter)
    options = {} if execution_guard is None else {'execution_guard': execution_guard}
    record = {"config": config, "files": inputs(config, **options), "environment": environment(**options),
              "implementation": code, "lock_sha256": filehash(CODE_ROOT/"requirements-dataset.lock.txt")}
    from .backends.common import fingerprint as backend_fingerprint
    record['environment']['backend'] = config.get('backend', 'icarus')
    if config.get('backend', 'icarus') != 'icarus':
        record['environment']['execution_backend'] = backend_fingerprint(config)
    return {"sha256": identity(record), "inputs": record}


def snapshot(config, destination, *, execution_guard=None):
    require_execution_guard(execution_guard)
    destination.mkdir(parents=True, exist_ok=False)
    options = {} if execution_guard is None else {'execution_guard': execution_guard}
    for path in inputs(config, **options):
        dst = destination/path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(input_path(config, path), dst)
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


def qualification_control(source, spec, operator):
    """Resolve the manifest's exact, registered checker-control edit."""
    if operator['id'] == 'literal_lsb_flip32':
        return locate_constant(source, spec['line'], spec['lhs'], spec['statement'])
    if operator['id'] == 'condition_invert':
        return locate_operator(source, spec['line'], operator['id'], spec['statement'],
                               path=spec['path'], reset_identifiers=spec['reset_identifiers'])
    return locate(source, spec['line'], spec['lhs'], spec['rhs_tail'], spec['statement'])


def qualify(*, execution_guard=None, destination=None):
    def guard():
        if execution_guard is not None and (not callable(execution_guard) or execution_guard() is not True):
            raise ValueError('Qualification execution readiness guard refused progress')
    guard()
    config = target.configuration(CONFIG)
    if config.get('backend', 'icarus') != 'icarus':
        if execution_guard is not None:
            raise ValueError('Guarded full qualification currently supports Icarus only')
        from .backends.proof import qualify_original
        return qualify_original(config)
    options = {} if execution_guard is None else {'execution_guard': execution_guard}
    fp = fingerprint(config, **options)
    guard()
    if destination is None:
        out = new_output("qualification", fp["sha256"][:12], config)
    else:
        out = Path(destination)
        if (not out.is_absolute() or out.is_symlink() or '..' in out.parts
                or any(p.is_symlink() for p in out.parents)
                or not out.is_relative_to(ROOT/'outputs'/config['target_id']/'qualification')):
            raise ValueError('Qualification destination must be fresh under its target qualification root')
        out.mkdir(parents=True, exist_ok=False)
    runner = Runner(out, config["limits"], execution_guard=execution_guard)
    save(out/"fingerprint.json", fp)
    golden = out/"original"
    snapshot(config, golden, **options)
    original_hashes = treehashes(golden)
    if original_hashes != fp['inputs']['files']:
        raise ValueError('Qualification snapshot differs from fingerprinted inputs')
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
    site = qualification_control(data, spec, operator)
    (control/spec["path"]).write_bytes(apply(data, site, operator))
    save(out/"negative_control.json", {"target": site, "path": spec["path"], "dataset_case": False})
    detected = simulate(runner, config, "control", control, compile_design(runner, config, "control", control))
    if detected["outcome"] != "functional_fail":
        raise RuntimeError(f"Checker did not detect control: {out}")
    guard()
    restored = out/'restored'
    shutil.copytree(control, restored)
    (restored/spec['path']).write_bytes(revert((restored/spec['path']).read_bytes(), site))
    if treehashes(restored) != original_hashes or treehashes(golden) != original_hashes:
        raise ValueError('Qualification restoration source identity failed')
    restored_verdict = simulate(runner, config, 'restored', restored,
        compile_design(runner, config, 'restored', restored))
    if restored_verdict['outcome'] != 'pass' or treehashes(restored) != original_hashes:
        raise ValueError('Qualification restored PASS/source identity failed')
    if fingerprint(config, **options) != fp:
        raise ValueError("Qualification inputs changed during execution")
    record = {"schema_version": "pilot-1", "design_id": config["design_id"], "status": "qualified",
              "fingerprint": fp["sha256"], "evidence": str(out.relative_to(ROOT)),
              "configuration": config, "baseline": baseline, "negative_control": detected,
              "restored": restored_verdict, "restoration": {"source_hashes": original_hashes,
                  "source_identity": True, "method": "exact reverse edit and whole-source identity"},
              "structure": structural, "scope": config["scope"],
              "tests": [{**config["test_metadata"], "id": config["test_id"]}]}
    schema(record, "design")
    guard()
    save(out/"design.json", record)
    # Preserve the exact implementation behind this qualification fingerprint.
    for relative, expected in fp["inputs"]["implementation"].items():
        if filehash(CODE_ROOT/relative) != expected:
            raise ValueError("Implementation changed before qualification publication")
        destination = out/"controller"/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CODE_ROOT/relative, destination)
    (out/'controller').mkdir(exist_ok=True)
    shutil.copyfile(CODE_ROOT/"requirements-dataset.lock.txt", out/"controller/requirements-dataset.lock.txt")
    manifest(out)
    guard()
    if execution_guard is not None and hasattr(execution_guard, 'before_publication'):
        if execution_guard.before_publication('qualification') is not True:
            raise ValueError('Scoped qualification publication refused')
    DESIGN.mkdir(parents=True, exist_ok=True)
    save(DESIGN/"design.json", record)
    write_dossier(record, runner.records)
    print(f"QUALIFIED {out}")


def qualified(*, execution_guard=None):
    target.configuration(CONFIG)  # Fail clearly when no target has been selected.
    if target.configuration(CONFIG).get('control', {}).get('pending'):
        raise ValueError('Original-only proof is not qualification: control and restored PASS remain pending')
    design = load(DESIGN/"design.json")
    schema(design, "design")
    config = target.configuration(CONFIG)
    options = {} if execution_guard is None else {'execution_guard': execution_guard}
    fp = fingerprint(config, **options)
    if design["fingerprint"] != fp["sha256"] or design["status"] != "qualified":
        raise ValueError("Stale/unqualified dossier: run qualify with current inputs")
    out = ROOT/design["evidence"]
    verify_manifest(out)
    if load(out/"design.json") != design:
        raise ValueError("Dossier does not match sealed qualification evidence")
    if config.get('backend', 'icarus') == 'icarus' and (
            design.get('restored', {}).get('outcome') != 'pass'
            or design.get('restoration', {}).get('source_identity') is not True
            or design.get('restoration', {}).get('source_hashes') != fp['inputs']['files']
            or treehashes(out/'restored') != fp['inputs']['files']):
        raise ValueError('Current qualification requires restored identity and PASS proof')
    return design, config, fp


def gates(original, mutants, restored, same_sources, *, record=None):
    policy_record = {} if record is None else record
    return {"original_pass": original["outcome"] == "pass",
            repeatability_check(policy_record): matching_mutant_failures(policy_record, mutants),
            "same_mutant_executable": len({m["executable_sha256"] for m in mutants}) == 1,
            "same_mutant_sources": len({identity(m["source_hashes"]) for m in mutants}) == 1,
            "restored_pass": restored["outcome"] == "pass", "restored_source_identity": same_sources}


def generate(proposal_path):
    # Legacy entry point now shares duplicate protection and durable recovery.
    from .batch import run
    return run(proposal_path, cap=1)


def _simulation_evidence(bundle, label, source, config, checker_config, checker_root):
    run = load(bundle/'commands'/label/'run.json')
    actual = classify((bundle/safe_path(run['stdout'])).read_text(), (bundle/safe_path(run['stderr'])).read_text(),
                      run['returncode'], run['timed_out'], config=checker_config, controller_root=checker_root)
    saved = load(bundle/(label+'.json'))
    if (run.get('interrupted') or any(saved.get(k) != v for k, v in actual.items())
            or saved['source_hashes'] != treehashes(source)):
        raise ValueError('Saved outcomes or source hashes disagree with evidence')
    binary = 'mutant.vvp' if label.startswith('mutant_') else label+'.vvp'
    if saved['executable_sha256'] != filehash(bundle/binary):
        raise ValueError('Executable identity mismatch')
    command = run['command']
    if (len(command) != 3 or command[:2] != ['vvp', '-N'] or not Path(command[2]).is_absolute()
            or Path(command[2]).name != binary):
        raise ValueError('Simulation command does not match recorded variant/executable')
    recorded_root = Path(command[2]).parent
    recorded_source = recorded_root/source.relative_to(bundle)
    if config.get('target_id') == 'aes':
        from .backends.icarus import simulation_cwd
        recorded_source = simulation_cwd(config, recorded_root, label, recorded_source)
    if run['cwd'] != str(recorded_source):
        raise ValueError('Simulation working directory does not match recorded variant')
    return saved, recorded_root


def _verify_command(bundle, name, args, cwd):
    run = load(bundle/'commands'/name/'run.json')
    if (run['command'] != [str(arg) for arg in args] or run['cwd'] != str(cwd)
            or run['returncode'] != 0 or run['timed_out'] or run.get('interrupted')):
        raise ValueError(f'Saved {name} command does not match successful execution')


def _verify_compile(bundle, label, config, recorded_root, cwd):
    _verify_command(bundle, label+'_compile', ['iverilog', *config['compile_flags'], '-s', config['test_top'],
                   '-o', recorded_root/(label+'.vvp'), *config['rtl'], config['testbench']], cwd)


def _verify_qualification_inputs(qualification, fp):
    config = fp['inputs']['config']
    if (load(qualification/'fingerprint.json') != fp
            or filehash(target.checker_path(config, qualification/'controller'))
            != fp['inputs']['implementation'][config['checker']['path']]):
        raise ValueError('Sealed qualification fingerprint or checker differs from case inputs')


def verified_original(qualification, fp, *, design=None):
    """Reparse the sealed qualification PASS for this exact runner fingerprint."""
    config = fp['inputs']['config']
    if config.get('backend', 'icarus') != 'icarus' or identity(fp['inputs']) != fp['sha256']:
        raise ValueError('Original PASS reuse requires an exact supported fingerprint')
    manifest_sha256 = filehash(qualification/'manifest.json')
    verify_manifest(qualification)
    _verify_qualification_inputs(qualification, fp)
    sealed = load(qualification/'design.json')
    schema(sealed, 'design')
    if (sealed['fingerprint'] != fp['sha256'] or sealed['configuration'] != config
            or (design is not None and design != sealed)):
        raise ValueError('Original PASS qualification inputs differ from case inputs')
    source = qualification/'original'
    if treehashes(source) != fp['inputs']['files']:
        raise ValueError('Original PASS source bytes differ from pinned inputs')
    saved, recorded_root = _simulation_evidence(qualification, 'original', source, config, config,
                                                qualification/'controller')
    _verify_compile(qualification, 'original', config, recorded_root, recorded_root/'original')
    if (saved != sealed['baseline'] or saved['outcome'] != 'pass' or saved['run_id'] != 'original'
            or saved['test_id'] != config['test_id'] or saved['seed'] != config['seed']
            or filehash(qualification/'manifest.json') != manifest_sha256):
        raise ValueError('Original PASS does not match sealed qualification evidence')
    return saved, {'qualification_manifest_sha256': manifest_sha256}


def audit(path, *, data_root=None, emit=True):
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
    current_policy = validation_policy(record) == CURRENT_VALIDATION_POLICY
    if current_policy and record['proposal']['baseline_fingerprint'] != frozen_fp['sha256']:
        raise ValueError('Case proposal does not bind the qualified fingerprint')
    plan = validation_plan(config, record['proposal']) if current_policy else None
    reused = current_policy and plan['original'] == 'reuse_qualification'
    if record["restored"] != load(path/"restored.json"):
        raise ValueError("Case summary disagrees with saved outcomes")
    count = mutant_run_count(record)
    if len(record['mutants']) != count or any(m != load(path/f'mutant_{i}.json') for i, m in enumerate(record['mutants'], 1)):
        raise ValueError(f'Case summary must contain exactly {count} saved mutant executions')
    checks = gates(record['original'], record['mutants'], record['restored'],
                   treehashes(original) == treehashes(restored), record=record)
    qual = Path(ROOT if data_root is None else data_root)/safe_path(record['qualification'])
    variants = [('restored', restored), *((f'mutant_{i}', buggy) for i in range(1, count+1))]
    if reused:
        saved, binding = verified_original(qual, frozen_fp)
        if (record['original'] != saved or record.get('original_reuse') != binding
                or any((path/entry).exists() for entry in ('original.json', 'original.vvp', 'commands/original',
                                                         'commands/original_compile'))):
            raise ValueError('Case original PASS reuse or replay evidence differs from its recorded policy')
    else:
        verify_manifest(qual)
        if load(qual/'design.json')['fingerprint'] != record['fingerprint']:
            raise ValueError('Reused qualification fingerprint differs')
        if current_policy:
            _verify_qualification_inputs(qual, frozen_fp)
        if record['original'] != load(path/'original.json'):
            raise ValueError('Case summary disagrees with saved original outcome')
        if current_policy and record.get('original_reuse') is not None:
            raise ValueError('Test-specific validation requires a fresh original PASS')
        variants.insert(0, ('original', original))
    if current_policy and count == 2 and any((path/entry).exists() for entry in ('mutant_3.json', 'commands/mutant_3')):
        raise ValueError('Case contains an unrequested third mutant simulation')
    checker_config, checker_root, checker_mode = historical_checker(
        config, qual/'controller', target.configuration(CONFIG) if CONFIG else None)
    recorded_roots = set()
    for label, source in variants:
        saved, recorded_root = _simulation_evidence(path, label, source, config, checker_config, checker_root)
        if current_policy and (saved['run_id'] != label or saved['test_id'] != config['test_id'] or saved['seed'] != config['seed']):
            raise ValueError('Saved simulation differs from the selected test or seed')
        recorded_roots.add(recorded_root)
    if len(recorded_roots) != 1:
        raise ValueError("Simulation commands reference inconsistent recorded case roots")
    if current_policy:
        recorded_root = recorded_roots.pop()
        restored_cwd = recorded_root/'rtl/restored'
        _verify_command(path, 'reverse_patch', ['patch', '-p1', '-R', '-i', recorded_root/'mutation.patch'], restored_cwd)
        _verify_compile(path, 'restored', config, recorded_root, restored_cwd)
        _verify_compile(path, 'mutant', config, recorded_root, recorded_root/'rtl/buggy')
        if not reused:
            _verify_compile(path, 'original', config, recorded_root, recorded_root/'rtl/original')
    if (not all(checks.values()) or not all(record['checks'].values())
            or (current_policy and any(record['checks'].get(key) != value for key, value in checks.items()))):
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
    result = {"audit_scope": "metadata_and_saved_execution_evidence", "result": "pass",
              "case_id": record["case_id"], "human_review": "pending", "fresh_simulations": 0,
              "checker_mode": checker_mode}
    if emit:
        print(__import__("json").dumps(result, indent=2))
    return result


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
