"""Backend contracts and recorded-log regression tests; never touch live data."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rtlprobe import pilot, target
from rtlprobe.backends import select
from rtlprobe.backends import common, uvm_patchset
from rtlprobe.evidence import CODE_ROOT, digest, identity, load, save, treehashes
from rtlprobe.oracle import classify

FIX = CODE_ROOT/'tests/fixtures/verilator'


def config(ip='rv_timer'):
    return load(CODE_ROOT/f'targets/opentitan_{ip}/config.json')


class BackendTests(unittest.TestCase):
    def test_selection_and_all_manifests(self):
        legacy = load(CODE_ROOT/'targets/sha256/config.json')
        self.assertEqual(select(legacy).__name__, 'rtlprobe.backends.icarus')
        for ip in ('crc32', 'rv_timer', 'uart'):
            c = config(ip)
            self.assertEqual(target.validate(c), c)
            self.assertTrue(select(c).__name__.endswith(c['backend']))
        with self.assertRaises(ValueError):
            select({'backend':'guess'})

    def test_reject_incomplete_test_identity_and_scoreboard_override(self):
        for key in ('oracle_kind','run_options','seed','sequence'):
            c = config(); del c['admitted_tests'][0][key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                target.validate(c)
        c = config()
        next(t for t in c['admitted_tests'] if t['id']=='same_csr_outstanding')['run_options'].append('+en_scb=1')
        with self.assertRaises(ValueError):
            target.validate(c)

    def test_uvm_recorded_pass_fail_truncation_timeout(self):
        c = config()
        good = (FIX/'uvm-pass.log').read_text()
        bad = (FIX/'uvm-fail.log').read_text()
        self.assertEqual(classify(good, config=c)['outcome'], 'pass')
        self.assertEqual(classify(good.replace('UVM_ERROR :', 'UVM_ERROR    :'), config=c)['outcome'], 'pass')
        result = classify(bad, config=c)
        self.assertEqual(result['outcome'], 'functional_fail')
        signature = result['signature'][0]
        self.assertEqual((signature['source'], signature['expected'], signature['actual']), ('scoreboard_check','0x1','0x0'))
        self.assertEqual(signature['simulation_time'], '605399359 ps')
        for text in (good[:good.index('--- UVM Report Summary ---')], good.replace('UVM_ERROR :    0','UVM_ERROR :    1'), good+'\nTEST PASSED CHECKS\n'):
            self.assertEqual(classify(text, config=c)['outcome'], 'infrastructure_error')
        self.assertEqual(classify(good, timed_out=True, config=c)['outcome'],'timeout_unclassified')
        self.assertEqual(classify('', config=c)['outcome'],'infrastructure_error')
        self.assertEqual(classify((FIX/'uvm-truncated.log').read_text(),config=c)['outcome'],'infrastructure_error')
        self.assertEqual(classify((FIX/'uvm-timeout.log').read_text(),timed_out=True,config=c)['outcome'],'timeout_unclassified')
        duplicate = classify((FIX/'uvm-duplicate-finish.log').read_text(),
                             config=dict(c, test_id='same_csr_outstanding'))
        self.assertEqual(duplicate['outcome'], 'infrastructure_error')
        self.assertEqual([entry['source'] for entry in duplicate['failures']], ['other', 'other'])

    def test_every_admitted_uvm_test_on_its_recorded_log(self):
        for ip in ('rv_timer','uart'):
            c=config(ip)
            for test in c['admitted_tests']:
                filename='uvm-pass.log' if test['id']=='rv_timer_random' else test['id']+'.log'
                selected=dict(c,test_id=test['id'])
                log=(FIX/filename).read_text()
                with self.subTest(test=test['id']):
                    result=classify(log,config=selected)
                    self.assertEqual(result['outcome'],'pass',result)
                    self.assertTrue(result['completion']['iterations'])
                    self.assertEqual(classify(log.replace(test['sequence'], 'wrong_sequence'),config=selected)['outcome'],'infrastructure_error')

    def test_mixed_oracle_signature_orientations(self):
        spec = importlib.util.spec_from_file_location('checker',CODE_ROOT/'targets/opentitan_uvm/checker.py')
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        cases = [('uart_smoke_vseq.sv','rx_byte == dut_rdata (33 [0x21] vs 0 [0x0])','register_model_read_compare','0x21','0x0'),
                 ('cip_base_vseq.sv','masked_data == exp_data (0 [0x0] vs 33 [0x21])','sequence_tl_compare','0x21','0x0'),
                 ('cip_base_vseq.sv','exp_val == act_val (33 [0x21] vs 0 [0x0])','register_model_read_compare','0x21','0x0'),
                 ('uart_base_vseq.sv','rdata == exp_data (0 [0x0] vs 9 [0x9])','register_model_read_compare','0x9','0x0'),
                 ('cip_base_vseq.sv','data & ~ro_mask == 0 (1 [0x1] vs 0 [0x0])','register_model_read_compare','0x0','0x1'),
                 ('cip_base_vseq.sv','rsp.d_error == exp_err_rsp (0 [0x0] vs 1 [0x1])','sequence_tl_compare','0x1','0x0'),
                 ('uart_scoreboard.sv','tx_processing_item_q.size() == 1 (0 [0x0] vs 1 [0x1])','scoreboard_check','0x1','0x0'),
                 ('uvm_seq.sv','randomization failed','other',None,None)]
        for file,msg,source,expected,actual in cases:
            line=f'UVM_ERROR @ 100 ps: ({file}:60) [test] Check failed {msg}'
            sig = module.failure(line)
            self.assertEqual((sig['source'],sig['expected'],sig['actual']), (source,expected,actual))

    def test_crc_recorded_values_and_completion(self):
        c=config('crc32');good=(FIX/'crc-pass.log').read_text();bad=(FIX/'crc-fail.log').read_text()
        self.assertEqual(classify(good,config=c)['comparisons_completed'],98)
        self.assertEqual(len(classify(bad,config=c)['signature']),97)
        self.assertEqual(classify(good.replace('Executed cycles:  104','Executed cycles:  103'),config=c)['outcome'],'infrastructure_error')
        self.assertEqual(classify(good.replace('00000000\n','',1),config=c)['outcome'],'infrastructure_error')

    def test_patch_exact_idempotent_and_wrong_upstream(self):
        before=b'first\nold\nlast\n';after=b'first\nnew\nlast\n'
        diff='--- a/unit.sv\n+++ b/unit.sv\n@@ -1,3 +1,3 @@\n first\n-old\n+new\n last\n'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); home=root/'patchset';(home/'patches').mkdir(parents=True)
            (home/'patches/unit.patch').write_text(diff)
            manifest=home/'patches/manifest.json'
            save(manifest, {'patches':[{'domain':'opentitan','targets':['test'],'path':'unit.sv','patch':'unit.patch',
                  'upstream_sha256':digest(before),'patched_sha256':digest(after),'diff_sha256':digest(diff.encode())}]})
            source=root/'source';source.mkdir();(source/'unit.sv').write_bytes(before)
            with patch.object(uvm_patchset,'HOME',home),patch.object(uvm_patchset,'MANIFEST',manifest):
                uvm_patchset.apply(source,'opentitan','test');self.assertEqual((source/'unit.sv').read_bytes(),after)
                hashes=treehashes(source);uvm_patchset.apply(source,'opentitan','test');self.assertEqual(hashes,treehashes(source))
                (source/'unit.sv').write_text('wrong\n')
                with self.assertRaisesRegex(ValueError,'Upstream hash'):
                    uvm_patchset.apply(source,'opentitan','test')

    def test_vendored_uvm_diffs_apply_to_pristine_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=uvm_patchset.unpack(Path(tmp)/'uvm')
            uvm_patchset.apply(root,'uvm','rv_timer')
            hashes=treehashes(root);uvm_patchset.apply(root,'uvm','rv_timer');self.assertEqual(hashes,treehashes(root))

    def test_new_file_shim_diff_and_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            uvm_patchset.apply(root,'shim','uart')
            self.assertEqual((root/'ot_uvm_compat.svh.upstream').read_bytes(),b'')
            self.assertIn('m_uvm_get_type_name_func',(root/'ot_uvm_compat.svh').read_text())
            before=treehashes(root);uvm_patchset.apply(root,'shim','uart');self.assertEqual(before,treehashes(root))

    def test_actual_backend_fingerprint_collects_fields(self):
        c=config()
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/'verilator';exe.write_text('fake tool')
            fs=Path(tmp)/'fusesoc';fs.write_text('fake fusesoc')
            def output(argv,**kwargs):
                if argv[0]=='git':return c['build']['verilator_git_sha']+'\n'
                if argv[0]==str(exe):return 'Verilator 5.053 devel rev v5.052-567-g0041d207c\n'
                return '2.4.5\n0.6.3\n'
            with patch.object(common,'tool',return_value=str(exe)),patch.object(common,'fusesoc',return_value=str(fs)),patch.object(common.subprocess,'check_output',side_effect=output),patch.dict(common.os.environ,{'RTLPROBE_VERILATOR_UVM_SOURCE':tmp}):
                result=common.fingerprint(c)
            self.assertEqual(result['verilator']['git_sha'],c['build']['verilator_git_sha'])
            self.assertEqual(len(result['uvm_tree_sha256']),64)
            self.assertEqual(len(result['library_edits']),3)
            self.assertEqual(result['library_configuration_edit'],'UVM_ENABLE_DEPRECATED_API')
            self.assertEqual(result['fusesoc'],'2.4.5')
            self.assertEqual(result['edalize'],'0.6.3')
            self.assertEqual(result['admitted_tests_sha256'],identity(c['admitted_tests']))
            self.assertEqual(len(result['diff_hashes']),23)

    def test_fingerprint_hash_binds_all_backend_fields(self):
        c=config()
        backend={'backend':'verilator_uvm','verilator':{'version':'5.053','git_sha':'a'},'uvm_tree_sha256':'b',
                 'library_edits':['c'],'patchset_manifest_sha256':'d','fusesoc':'2.4.5','edalize':'0.6.3','admitted_tests_sha256':'e'}
        with patch.object(pilot,'inputs',return_value={}),patch.object(pilot,'environment',return_value={}):
            with patch.object(common,'fingerprint',return_value=backend):
                initial=pilot.fingerprint(c)
                self.assertEqual(initial['inputs']['environment']['execution_backend'],backend)
            for key in backend:
                changed=copy.deepcopy(backend);changed[key]='changed'
                with self.subTest(field=key),patch.object(common,'fingerprint',return_value=changed):
                    self.assertNotEqual(initial['sha256'],pilot.fingerprint(c)['sha256'])

    def test_binary_source_binding_rejects_changed_source_before_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir();(source/'rtl.sv').write_text('original')
            obj=root/'build/obj';obj.mkdir(parents=True);binary=obj/'Vtb';binary.write_text('executable')
            save(obj.parent/'build.json',{'source_hashes':treehashes(source),'executable_sha256':digest(binary.read_bytes())})
            (source/'rtl.sv').write_text('different RTL')
            with self.assertRaisesRegex(ValueError,'rebuild required'):
                common.run(None,config(),'changed',source,binary)


if __name__=='__main__':
    unittest.main()
