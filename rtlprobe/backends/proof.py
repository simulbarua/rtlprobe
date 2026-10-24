"""Original-only evidence; deliberately cannot create a qualified design dossier."""
import json
import shutil
from .. import pilot
from ..evidence import CODE_ROOT, Runner, filehash, identity, load, manifest, save


def qualify_original(config):
    fp = pilot.fingerprint(config)
    out = pilot.new_output('original-proof', fp['sha256'][:12], config)
    runner = Runner(out, config['limits'])
    save(out/'fingerprint.json', fp)
    for relative in fp['inputs']['implementation']:
        destination = out/'controller'/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CODE_ROOT/relative, destination)
    shutil.copyfile(CODE_ROOT/'requirements-dataset.lock.txt', out/'controller/requirements-dataset.lock.txt')
    shutil.copytree(CODE_ROOT/'tooling/verilator-uvm', out/'controller/tooling/verilator-uvm')
    source = out/'original' 
    pilot.snapshot(config, source)
    binary = pilot.compile_design(runner, config, 'original', source)
    results = []
    for test in config['admitted_tests']:
        selected = dict(config, test_id=test['id'])
        result = pilot.simulate(runner, selected, 'original_'+test['id'], source, binary)
        results.append(result)
        print('ORIGINAL_PROOF '+json.dumps({
            'target': config['target_id'], 'test': test['id'], 'outcome': result['outcome'],
            'oracle_kind': test['oracle_kind'], 'source_sha256': identity(result['source_hashes']),
            'executable_sha256': result['executable_sha256'],
            'result_sha256': filehash(out/(result['run_id']+'.json')),
            'run_wall_seconds': result['run_wall_seconds'],
            'checker_proof': result.get('completion', {'comparisons_completed':result.get('comparisons_completed')})}, sort_keys=True), flush=True)
        if result['outcome'] != 'pass':
            raise RuntimeError(f'Original checker proof failed: {out}')
    if pilot.fingerprint(config) != fp:
        raise ValueError(f'Inputs changed during original proof; not sealed: {out}')
    record = {'schema_version':'original-proof-1', 'status':'original_pass_only',
              'fingerprint': fp['sha256'], 'target': config['target_id'], 'results':results,
              'control':config['control'], 'restored':'pending front end', 'gate_1_complete':False,
              'build': load(binary.parent.parent/'build.json')}
    save(out/'original-proof.json',record)
    manifest(out)
    print('ORIGINAL_PROOF_COMPLETE '+json.dumps({'target':config['target_id'],
          'evidence':str(out),'fingerprint':fp['sha256'],'manifest_sha256':filehash(out/'manifest.json'),
          'build_walltime_seconds':record['build']['walltime_seconds'],
          'control':'pending front end','restored':'pending front end','gate_1_complete':False},sort_keys=True),flush=True)
    return record
