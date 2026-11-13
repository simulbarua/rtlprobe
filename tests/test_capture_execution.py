"""Private capture proof fixtures; all native/model processes are forbidden."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_evidence_capture import fixture
from rtlprobe import capture_execution as proof, evidence_capture as capture
from rtlprobe.evidence import CODE_ROOT, filehash, identity, save
from rtlprobe.evidence_observer import instrument_testbench
from rtlprobe.evidence_structure import observer_source


def executed_fixture(root, config=None, payload=None):
    """Write synthetic Runner-shaped records, never a claim of real execution."""
    payload = fixture() if payload is None else payload
    if config is None:
        config = {'target_id':'sha256','top':'m','test_top':'tb','test_id':'upstream_core_all',
                  'rtl':['rtl.v'],'testbench':'tb.v','compile_flags':['-g2005'],
                  'test_metadata':{'checkpoints':payload['checker']['context']['checkpoints']},
                  'limits':{'compile_seconds':60,'simulation_seconds':15,'campaign_seconds':600,
                            'cpu_seconds':480,'disk_bytes':268435456}}
    root=Path(root).resolve();work=root/'work';work.mkdir(parents=True)
    for name,text in {**payload['buggy_sources'],**payload['checker']['testbench_source']}.items():
        path=work/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(text.encode())
    expected={p:filehash(work/p) for p in config['rtl']+[config['testbench']]}
    observer,policy=observer_source(payload['graph'])
    observed,checker_policy=instrument_testbench((work/config['testbench']).read_bytes().decode(),config['target_id'])
    (work/'observer.v').write_bytes(observer.encode());(work/'observed_tb.v').write_bytes(observed.encode())
    (work/'buggy.vcd').write_bytes(payload['trace']['raw_vcd'].encode())
    for phase in ('plain_buggy','observed_buggy'):
        (work/(phase+'.vvp')).write_text('.scope module, "tb" "tb";\n .timescale -9 -9;\n')
    records=[];limit=min(64*1024*1024,config['limits']['disk_bytes']//4)
    for name,command,timeout in proof.command_plan(root,config,limit):
        directory=root/'commands'/name;directory.mkdir(parents=True)
        log=payload['checker']['observed_buggy_log' if name.startswith('observed') else 'plain_buggy_log'] if name.endswith('_run') else {'stdout':'','stderr':'','returncode':0,'timed_out':False}
        for stream in ('stdout','stderr'):(directory/(stream+'.log')).write_text(log[stream])
        start={'id':name,'command':command,'cwd':str(work),'started_at':datetime.now(timezone.utc).isoformat(),'timeout_seconds':timeout}
        record={**start,'returncode':log['returncode'],'timed_out':False,'interrupted':False,
                'elapsed_seconds':0.01,'cpu_seconds':0.001,
                **{stream:f'commands/{name}/{stream}.log' for stream in ('stdout','stderr')},
                **{stream+'_sha256':filehash(directory/(stream+'.log')) for stream in ('stdout','stderr')}}
        save(directory/'started.json',start);save(directory/'process.json',{'pid':12345});save(directory/'run.json',record)
        records.append(record)
    save(root/'commands.json',records)
    provenance={'schema_version':'capture-provenance-1','snapshot_kind':'buggy','input_hashes':expected,
        'target_config_sha256':identity(config),'checker_adapter_sha256':filehash(CODE_ROOT/f"targets/{config['target_id']}/checker.py"),
        'records':records,'observer_policy':policy,'checker_observer_policy':checker_policy,
        'observed_testbench_sha256':filehash(work/'observed_tb.v'),'compiled_vvp_sha256':filehash(work/'observed_buggy.vvp'),
        'runtime_file_limit':{'mechanism':'RLIMIT_FSIZE','bytes':limit},'capture_status':'complete'}
    capture.publish_companion(root/'companion',payload,provenance=provenance)
    binding=proof.seal_capture_execution(root,config=config,expected_hashes=expected)
    return config,expected,binding


class CaptureExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()/'capture'
        for item in (patch('subprocess.Popen',side_effect=AssertionError('No native/model execution')),
                     patch.object(proof.shutil,'which',return_value=sys.executable)):
            item.start();self.addCleanup(item.stop)
        self.config,self.expected,self.bound=executed_fixture(self.root)

    def verify(self):
        return proof.verify_capture_execution(self.bound['path'],expected_sha256=self.bound['sha256'],
            config=self.config,expected_hashes=self.expected)

    def rehash_work(self):
        path=Path(self.bound['path']);value=json.loads(path.read_text());value['files']=proof._files(self.root)
        save(path,value);self.bound['sha256']=filehash(path)

    def test_actual_shaped_command_proof_roundtrip_and_external_hash_required(self):
        self.assertEqual(self.verify()['checker']['observational_parity'],'matched')
        self.bound['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'proof'):self.verify()

    def test_raw_work_tampering_additions_missing_records_and_symlinks_refuse(self):
        for relative in ('work/observed_tb.v','work/observed_buggy.vvp','work/buggy.vcd',
                         'commands/plain_buggy_run/stdout.log','commands/observed_buggy_run/process.json'):
            path=self.root/relative;before=path.read_bytes();path.write_bytes(before+b' ')
            with self.subTest(path=relative),self.assertRaises(ValueError):self.verify()
            path.write_bytes(before)
        path=self.root/'unexpected';path.write_text('extra')
        with self.assertRaises(ValueError):self.verify()
        path.unlink();path.symlink_to(self.root/'work/rtl.v')
        with self.assertRaises(ValueError):self.verify()

    def test_rehashing_fake_provenance_does_not_supply_missing_command_history(self):
        path=self.root/'commands/plain_buggy_run/run.json';path.unlink();self.rehash_work()
        with self.assertRaises((ValueError,FileNotFoundError)):self.verify()

    def test_wrong_runtime_config_inputs_and_offline_import_cannot_admit(self):
        original=self.config;self.config={**original,'compile_flags':['-g2012']}
        with self.assertRaises(ValueError):self.verify()
        self.config=original
        with patch.object(proof,'runtime_binding',return_value={'wrong':'runtime'}):
            with self.assertRaises(ValueError):self.verify()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();capture.publish_companion(root/'companion',fixture(),
                provenance={'schema_version':'offline-import-1','fresh_simulations':0})
            self.assertEqual(capture.load_inference_evidence(root/'companion')['trace']['status'],'complete')
            with self.assertRaises((ValueError,FileNotFoundError)):
                proof.seal_capture_execution(root,config=original,expected_hashes=self.expected)

    def test_rehashed_changed_command_is_not_complete_execution(self):
        provenance_path=self.root/'companion/provenance.json'
        before=provenance_path.read_bytes()
        provenance=json.loads(before);provenance['records'][0]['command'][0]='unapproved-command'
        save(provenance_path,provenance)
        # Even if a caller rebinds the companion manifest and proof, actual argv,
        # commands.json and run.json still have to agree with the fixed plan.
        manifest=self.root/'companion/manifest.json';value=json.loads(manifest.read_text())
        value['files']['provenance.json']=filehash(provenance_path);save(manifest,value)
        path=Path(self.bound['path']);value=json.loads(path.read_text());value['companion_manifest_sha256']=filehash(manifest)
        save(path,value);self.rehash_work()
        with self.assertRaises(ValueError):self.verify()

    def test_consistently_rehashed_timeout_and_resource_violations_refuse(self):
        for changes in ({'timed_out':True}, {'interrupted':True},
                        {'cpu_seconds':481}, {'elapsed_seconds':62},
                        {'timeout_seconds':0}, {'cpu_seconds':float('inf')}):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp).resolve()/'capture'
                config,expected,bound=executed_fixture(root)
                provenance_path=root/'companion/provenance.json'
                provenance=json.loads(provenance_path.read_text())
                provenance['records'][0].update(changes)
                save(provenance_path,provenance)
                save(root/'commands.json',provenance['records'])
                save(root/'commands/plain_buggy_compile/run.json',provenance['records'][0])
                if 'timeout_seconds' in changes:
                    start=root/'commands/plain_buggy_compile/started.json'
                    value=json.loads(start.read_text());value.update(changes);save(start,value)
                manifest=root/'companion/manifest.json';value=json.loads(manifest.read_text())
                value['files']['provenance.json']=filehash(provenance_path);save(manifest,value)
                path=Path(bound['path']);value=json.loads(path.read_text())
                value['companion_manifest_sha256']=filehash(manifest);value['files']=proof._files(root)
                save(path,value)
                with self.assertRaises(ValueError):
                    proof.verify_capture_execution(path,expected_sha256=filehash(path),
                        config=config,expected_hashes=expected)
