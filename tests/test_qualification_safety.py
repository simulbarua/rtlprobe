"""Fresh qualifier restoration/publication guards; all native execution mocked."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rtlprobe import pilot
from rtlprobe.evidence import CODE_ROOT,filehash,load,treehashes
from rtlprobe.mutation import sha

SOURCE=b'module m;\nreg [31:0] a,b,c;\nalways @* begin\n a = b + c;\nend\nendmodule\n'


class QualificationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.out=self.root/'outputs/qualification/new';self.design=self.root/'design'
        self.config=copy.deepcopy(load(CODE_ROOT/'targets/sha256/config.json'))
        self.config.update(top='m',test_top='tb',rtl=['rtl.v'],testbench='tb.v',collateral=[],
            control={'path':'rtl.v','line':4,'lhs':'a','rhs_tail':'c','statement':'a = b + c;',
                     'operator':{'id':'unsigned32_root_add_to_sub','version':'1.0'}})
        self.files={'rtl.v':SOURCE,'tb.v':b'module tb; endmodule\n'}
        self.fp={'sha256':'f'*64,'inputs':{'files':{p:sha(b) for p,b in self.files.items()},'implementation':{}}}
        self.phases=[];self.fail=None;self.enabled=True;self.revoke_after=None;self.corrupt_control=False
        def snapshot(config,destination,**unused):
            destination.mkdir(parents=True)
            for p,b in self.files.items():(destination/p).write_bytes(b)
        def simulate(runner,config,name,source,binary):
            self.phases.append(name)
            if name=='control' and self.corrupt_control:(source/'tb.v').write_bytes(b'changed checker')
            if self.revoke_after==name:self.enabled=False
            outcome=('functional_fail' if name=='control' else 'pass')
            if self.fail==name:outcome='pass' if name=='control' else 'infrastructure_error'
            return {'outcome':outcome,'source_hashes':treehashes(source),'run_id':name}
        for item in (patch.object(pilot,'ROOT',self.root),patch.object(pilot,'DESIGN',self.design),
                     patch.object(pilot.target,'configuration',return_value=self.config),
                     patch.object(pilot,'fingerprint',return_value=self.fp),patch.object(pilot,'new_output',return_value=self.out),
                     patch.object(pilot,'snapshot',side_effect=snapshot),patch.object(pilot,'simulate',side_effect=simulate),
                     patch.object(pilot,'compile_design',return_value=self.root/'synthetic-binary'),
                     patch.object(pilot,'structure',return_value={'status':'pass'}),patch.object(pilot,'write_dossier'),
                     patch('subprocess.Popen',side_effect=AssertionError('No target execution authorized'))):
            item.start();self.addCleanup(item.stop)

    def run_qualify(self):pilot.qualify(execution_guard=lambda:self.enabled)

    def test_restored_tree_pass_and_three_phases_required_before_current_dossier(self):
        self.run_qualify();record=load(self.design/'design.json')
        self.assertEqual(self.phases,['original','control','restored'])
        self.assertEqual(record['restored']['outcome'],'pass')
        self.assertIs(record['restoration']['source_identity'],True)
        self.assertEqual(treehashes(self.out/'original'),treehashes(self.out/'restored'))
        self.assertNotEqual(treehashes(self.out/'original'),treehashes(self.out/'control'))
        self.assertEqual(pilot.qualified()[0],record)

    def test_each_failed_phase_cannot_publish_qualified_dossier(self):
        for phase in ('original','control','restored'):
            with self.subTest(phase=phase):
                self.fail=phase
                # Each attempt has its own isolated output, with no implicit retry.
                self.out=self.root/'outputs'/phase
                pilot.new_output.return_value=self.out
                with self.assertRaises((ValueError,RuntimeError)):self.run_qualify()
                self.assertFalse((self.design/'design.json').exists())

    def test_corrupted_checker_cannot_restore_or_publish(self):
        self.corrupt_control=True
        with self.assertRaisesRegex(ValueError,'restoration'):self.run_qualify()
        self.assertEqual(self.phases,['original','control'])
        self.assertFalse((self.design/'design.json').exists())

    def test_guard_refusal_and_mid_check_revocation_prevent_publication(self):
        self.enabled=False
        with self.assertRaisesRegex(ValueError,'guard'):self.run_qualify()
        self.assertFalse(self.out.exists())
        self.enabled=True;self.revoke_after='control'
        with self.assertRaisesRegex(ValueError,'guard'):self.run_qualify()
        self.assertEqual(self.phases,['original','control'])
        self.assertFalse((self.out/'restored').exists());self.assertFalse((self.design/'design.json').exists())

    def test_publication_guard_denies_revocation_after_restored_pass(self):
        self.revoke_after='restored'
        with self.assertRaisesRegex(ValueError,'guard'):self.run_qualify()
        self.assertFalse((self.design/'design.json').exists())
