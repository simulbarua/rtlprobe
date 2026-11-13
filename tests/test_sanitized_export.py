"""Synthetic offline export boundaries; no target process or real dataset IO."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from rtlprobe import sanitized_export as export
from rtlprobe.evidence_capture import build_inference_evidence, publish_companion

SOURCES = {'dut.v': 'module dut(input wire a, b, output wire y);\nassign y = a & b;\nendmodule\n'}
TB = 'module tb; reg a, b; wire y; dut dut(.a(a), .b(b), .y(y)); endmodule\n'
VCD = '''$timescale 1 ns $end
$scope module tb $end
$scope module dut $end
$var wire 1 ! a $end
$var wire 1 " b $end
$var wire 1 # y $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
0!
0"
0#
#10
1!
1"
1#
'''
FAIL = '''-- Testbench for sha256 core started --
*** TC 1 single block test case started.
*** ERROR: TC 1 NOT successful.
Expected: 0x'''+('a'*64)+'''
Got:      0x'''+('b'*64)+'''
*** TC 2 double block test case started.
*** TC 2 first block successful
*** TC 2 second block successful
Running test for 9 block issue.
Digest ok.
*** 01 test cases did not complete successfully.
*** Simulation done.
'''


class SanitizedExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.curator = self.root/'curator'
        self.curator.mkdir()
        log = {'stdout': FAIL, 'stderr': '', 'returncode': 0, 'timed_out': False}
        self.evidence = build_inference_evidence(buggy_sources=SOURCES, top='dut', dut_scope='tb.dut',
            raw_vcd=VCD, checker_context={'target_id': 'sha256', 'test_id': 'upstream',
                'checkpoints': ['tc1', 'tc2_block1', 'tc2_block2', 'issue9']},
            testbench_source={'tb.v': TB}, plain_buggy_log=log, observed_buggy_log=log)
        self.snapshot = export.identity(self.evidence['source_hashes'])
        def common_source(path, role, text):
            return {'path': path, 'roles': [role], 'content': text, 'snapshot_sha256': self.snapshot}
        self.common = {'configuration': {'top': 'dut', 'test_top': 'tb', 'test_id': 'upstream',
            'rtl': ['dut.v'], 'testbench': 'tb.v', 'defines': [], 'parameters': {}, 'seed': None,
            'control': {'operator': 'must stay private'}, 'vendor': '/home/private/vendor',
            'specification': {'requirement': 'legacy mutation-specific requirement'}},
            'sources': [common_source('tb.v', 'testbench', TB),
                        *[common_source(path, 'checker', text) for path, text in self.evidence['checker']['adapter_source'].items()],
                        common_source('README.md', 'documentation', 'Synthetic DUT description\n')],
            'logs': [{'test_id': 'upstream', 'outcome': 'functional_fail', 'text': FAIL,
                      'snapshot_sha256': self.snapshot}], 'hierarchy': self.evidence['graph']['instances']}
        self.spec = self.curator/'spec'
        (self.spec/'sections').mkdir(parents=True)
        (self.spec/'README.md').write_text('Private retrieval: /Users/owner/project/qualification/abc/original\n')
        (self.spec/'requirements.jsonl').write_text('{"id":"req.output","text":"Output equals conjunction."}\n')
        (self.spec/'schema.json').write_text('{}\n')
        (self.spec/'sections/01-function.md').write_text('Section 1: Output is the conjunction of the inputs.\n')
        (self.spec/'sources.json').write_text(json.dumps({'standard': {'title': 'Synthetic standard',
            'url': 'https://example.com/standard', 'version': '1', 'license': 'fixture',
            'path': '/Users/owner/project/qualification/abc/original/README.md',
            'snapshot': '/home/developer/project/qualification/def/original',
            'files_sha256': {'dut.v': '0'*64}, 'files': ['dut.v']}}))
        _, self.spec_hash = export.specification_files(self.spec)

    def tearDown(self):
        for path in [self.root, *(p for p in self.root.rglob('*') if p.is_dir())]:
            path.chmod(0o755)
        self.temporary.cleanup()

    def make(self, condition='C0', name=None, **overrides):
        destination = self.root/'exports'/(name or condition)
        values = dict(evidence=self.evidence, condition=condition, neutral_id='sample-'+'a'*16,
            common_context=self.common, curator_root=self.curator, evidence_binding_sha256='1'*64,
            specification=self.spec, specification_sha256=self.spec_hash,
            raw_vcd=VCD, allow_partial=condition != 'C0')
        values.update(overrides)
        result = export.export_evidence(destination, **values)
        return destination, result

    def test_conditions_share_all_candidates_and_withhold_other_modalities(self):
        inventories = []
        for condition in export.CONDITIONS:
            directory, manifest = self.make(condition)
            export.verify_export(directory, expected_manifest_sha256=export.sha((directory/'manifest.json').read_bytes()))
            inventories.append((directory/'candidates.json').read_bytes())
            names = set(manifest['files'])
            self.assertEqual('specification/requirements.jsonl' in names, condition in {'C3', 'C4', 'M'})
            self.assertEqual('structure/alignment.json' in names, condition in {'C1', 'C4'})
            # Anchorless developer fixtures cannot expose an unselected full run.
            self.assertNotIn('raw/buggy.vcd', names)
            self.assertNotIn('raw/windows.json', names)
            self.assertEqual('raw/graph.json' in names, condition == 'M')
            common = json.loads((directory/'common.json').read_text())
            self.assertEqual(set(common['configuration']), export.CONFIG_FIELDS)
            self.assertNotIn('legacy mutation-specific requirement', (directory/'common.json').read_text())
        self.assertTrue(all(value == inventories[0] for value in inventories))

    def test_spec_metadata_projection_is_fixed_and_original_store_unchanged(self):
        before = {p.relative_to(self.spec).as_posix(): p.read_bytes() for p in self.spec.rglob('*') if p.is_file()}
        a, first = self.make('C3')
        b, second = self.make('C4')
        for name in ('requirements.jsonl', 'schema.json', 'sections/01-function.md'):
            self.assertEqual((a/'specification'/name).read_bytes(), before[name])
        bibliography = json.loads((a/'specification/sources.json').read_text())['standard']
        self.assertEqual(set(bibliography), {'title', 'url', 'version', 'license'})
        self.assertEqual((a/'specification/sources.json').read_bytes(), (b/'specification/sources.json').read_bytes())
        self.assertEqual(first['specification_sha256'], second['specification_sha256'])
        self.assertNotEqual(first['specification_sha256'], self.spec_hash)
        self.assertEqual(before, {p.relative_to(self.spec).as_posix(): p.read_bytes() for p in self.spec.rglob('*') if p.is_file()})
        with self.assertRaisesRegex(ValueError, 'independent frozen binding'):
            self.make('C3', 'bad-spec', specification_sha256='0'*64)

    def test_window_projection_keeps_start_state_and_withholds_later_failures(self):
        from vcdvcd import VCDVCD
        raw = VCD+'#20\n0!\n#30\n0"\n#40\n0#\n'
        window = export._vcd_window(raw, 5, 15)
        parsed = VCDVCD(vcd_string=window)
        self.assertEqual(parsed.begintime, 5)
        self.assertEqual(parsed.endtime, 15)
        self.assertEqual(parsed['tb.dut.a'].tv, [(5, '0'), (10, '1')])
        self.assertNotIn('#20', window)
        self.assertNotIn('#30', window)
        views_input = copy.deepcopy(self.evidence)
        views_input['trace'].update(raw_vcd=raw, analysis_window={'start_tick': 0, 'end_tick': 10},
            passing_test_windows=[{'checkpoint': 'pass1', 'start_tick': 25, 'end_tick': 30}],
            reset={'status': 'observed'}, status='complete')
        raw_files, selection, aligned = export.waveform_views(views_input)
        self.assertEqual(set(raw_files), {'raw/failure.vcd', 'raw/pass-001.vcd'})
        self.assertEqual([row['end_tick'] for row in selection['windows']], [10, 30])
        self.assertEqual([row['history']['capture_end_tick'] for row in aligned['windows']], [10, 30])
        self.assertNotIn('#40', raw_files['raw/pass-001.vcd'].decode())

    def test_icarus_parameter_comment_and_empty_dumpall_preserve_window(self):
        decorated = VCD.replace('#0', '$comment Show the parameter values. $end\n$dumpall\n$end\n#0', 1)
        self.assertEqual(export._vcd_window(decorated, 0, 10), export._vcd_window(VCD, 0, 10))

    def test_finish_path_normalization_is_bound_and_keeps_private_log_immutable(self):
        source='module tb;\ninitial $finish;\nendmodule\n'
        text='checker verdict unchanged\n/home/private/case/work/src/tb.v:2: $finish called at 42 (1s)\n'
        normalized=export._public_log_text(text,{'src/tb.v':source})
        self.assertEqual(normalized,'checker verdict unchanged\nsrc/tb.v:2: $finish called at 42 (1s)\n')
        self.assertIn('/home/private/',text)
        for changed in (text.replace('tb.v:2','other.v:2'),text.replace('tb.v:2','tb.v:1'),
                        text.replace('$finish called','$display called')):
            self.assertEqual(export._public_log_text(changed,{'src/tb.v':source}),changed)
            with self.assertRaises(ValueError):export.leakage_check(changed)

    def test_dumpall_values_and_multiline_comments_preserve_order_and_seed(self):
        from vcdvcd import VCDVCD
        raw = VCD.replace('#10\n1!', '#10\n$comment metadata\n#999\nignored text\n$end\n$dumpall\n1!')
        raw = raw.rstrip()+'\n$end\n#20\n0!\n'
        window = export._vcd_window(raw, 5, 15)
        self.assertEqual(VCDVCD(vcd_string=window)['tb.dut.a'].tv, [(5,'0'),(10,'1')])
        self.assertIn('#10\n1!\n1"\n1#',window)
        self.assertNotIn('ignored text',window)
        self.assertNotIn('#999',window)
        self.assertNotIn('#20',window)

    def test_malformed_and_unknown_waveform_directives_refuse(self):
        for body in ('$unsupported\n', '$end\n', '$dumpall\n$dumpvars\n$end\n$end\n',
                     '$dumpall\n#0\n$end\n', '$comment unterminated\n',
                     '$comment text $end trailing\n', '$dumpall\n'):
            with self.subTest(body=body), self.assertRaises(ValueError), patch(
                    'vcdvcd.VCDVCD', side_effect=AssertionError('Malformed framing reached third-party reader')):
                export._vcd_window(VCD+body,0,10)

    def test_checked_windows_export_identical_raw_information_to_c2_c4_and_m(self):
        from rtlprobe.evidence_observer import compiled_timebase
        source = ('module dut(input wire reset_n, input wire [255:0] digest_in, output wire [255:0] digest);\n'
                  'assign digest = digest_in;\nendmodule\n')
        tb = ('module tb; reg reset_n; reg [255:0] digest_in; wire [255:0] digest; '
              'dut dut(.reset_n(reset_n), .digest_in(digest_in), .digest(digest)); endmodule\n')
        bits_a = ''.join(format(int(c, 16), '04b') for c in 'a'*64)
        bits_b = ''.join(format(int(c, 16), '04b') for c in 'b'*64)
        raw = ('''$timescale 1 ns $end
$scope module tb $end
$scope module dut $end
$var wire 1 ! reset_n $end
$var wire 256 " digest_in [255:0] $end
$var wire 256 # digest [255:0] $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
0!
b0 "
b0 #
#1
1!
#5
'''+f'b{bits_b} "\nb{bits_b} #\n#10\nb{bits_a} "\nb{bits_a} #\n#25\nb0 "\nb0 #\n')
        checkpoints = ['tc1', 'tc2_block1', 'tc2_block2', 'issue9']
        diagnostic = []
        for index, checkpoint in enumerate(checkpoints):
            expected, actual = 'a'*64, ('b'*64 if index == 0 else 'a'*64)
            diagnostic += [f'RTLPROBE_WINDOW checkpoint={checkpoint} start_units={index*5+2}',
                           f'RTLPROBE_OBSERVE checkpoint={checkpoint} time_units={(index+1)*5} expected={expected} actual={actual}']
        plain = {'stdout': FAIL, 'stderr': '', 'returncode': 0, 'timed_out': False}
        observed = dict(plain, stdout='\n'.join(diagnostic)+'\n'+FAIL)
        evidence = build_inference_evidence(buggy_sources={'dut.v': source}, top='dut', dut_scope='tb.dut',
            raw_vcd=raw, checker_context={'target_id': 'sha256', 'test_id': 'upstream', 'checkpoints': checkpoints},
            testbench_source={'tb.v': tb}, plain_buggy_log=plain, observed_buggy_log=observed,
            timebase=compiled_timebase('S .scope module, "tb" "tb" 0 0;\n .timescale -9 -9;\n', 'tb'))
        common = copy.deepcopy(self.common)
        common['hierarchy'] = evidence['graph']['instances']
        for row in common['sources'] + common['logs']:
            row['snapshot_sha256'] = export.identity(evidence['source_hashes'])
        common['sources'][0]['content'] = tb
        windows, checkers = [], []
        self.assertEqual(len(evidence['checker']['anchors']), 4)
        for condition in export.CONDITIONS:
            directory, manifest = self.make(condition, name='anchored-'+condition, evidence=evidence,
                common_context=common, raw_vcd=raw, allow_partial=False)
            self.assertTrue(manifest['ready'])
            export.verify_export(directory)
            checker_bytes=(directory/'checker.json').read_bytes();checkers.append(checker_bytes)
            checker=json.loads(checker_bytes)
            self.assertEqual(set(checker),{'schema_version','context','testbench_source','adapter_source','plain_buggy_log','verdict'})
            self.assertEqual(checker['schema_version'],'public-buggy-checker-1')
            self.assertEqual(checker['plain_buggy_log'],plain)
            self.assertEqual(checker['verdict'],evidence['checker']['verdict'])
            self.assertNotIn('RTLPROBE_OBSERVE',checker['plain_buggy_log']['stdout'])
            if condition in ('C2','C4','M'):
                windows.append({name: (directory/name).read_bytes() for name in manifest['files']
                                if name.startswith('raw/') and name.endswith('.vcd')})
        self.assertTrue(all(value==checkers[0] for value in checkers))
        self.assertEqual(windows[0], windows[1])
        self.assertEqual(windows[0], windows[2])
        self.assertTrue(all(b'#25' not in value for value in windows[0].values()))

    def test_verifier_refuses_private_or_nested_checker_alignment_even_with_bound_hashes(self):
        mutations=[lambda c:{**c,'anchors':[{'signal':'tb.dut.y','tick':10}]},
                   lambda c:{**c,'verdict':{**c['verdict'],'timebase':{'tick_seconds':'1e-9'}}},
                   lambda c:{**c,'plain_buggy_log':{**c['plain_buggy_log'],
                       'stdout':'RTLPROBE_OBSERVE checkpoint=tc1 time_units=10\n'+c['plain_buggy_log']['stdout']}},
                   lambda c:self.evidence['checker']]
        for index,mutate in enumerate(mutations):
            with self.subTest(index=index):
                directory,_=self.make(name='nested-checker-'+str(index))
                checker=directory/'checker.json';checker.chmod(0o644)
                checker.write_bytes(export.encoded(mutate(json.loads(checker.read_text()))));checker.chmod(0o444)
                path=directory/'manifest.json';manifest=json.loads(path.read_text())
                manifest['files']['checker.json']=export.sha(checker.read_bytes())
                path.chmod(0o644);path.write_bytes(export.encoded(manifest));path.chmod(0o444)
                with self.assertRaises(ValueError):
                    export.verify_export(directory,expected_manifest_sha256=export.sha(path.read_bytes()))

    def test_strict_exports_refuse_imported_multidimensional_memory_without_waveforms(self):
        from test_evidence_capture import fixture,SOURCE,waveform
        from rtlprobe.evidence_capture import load_inference_evidence
        source=SOURCE.replace('mem [0:1]','mem [0:1][0:1]').replace('mem[0] =','mem[0][0] =').replace('mem[1] =','mem[1][1] =')
        raw='\n'.join(line for line in waveform(missing_word=True).splitlines()
                      if not line.startswith('$var reg 32 #') and line!='b0 #')+'\n'
        evidence=fixture(buggy_sources={'rtl.v':source},raw_vcd=raw)
        companion=publish_companion(self.curator/'partial-memory',evidence,provenance={'synthetic':True})
        evidence=load_inference_evidence(companion)
        snapshot=export.identity(evidence['source_hashes'])
        def row(path,role,text):return {'path':path,'roles':[role],'content':text,'snapshot_sha256':snapshot}
        common={'configuration':{'top':'m','test_top':'tb','test_id':evidence['checker']['context']['test_id'],
            'rtl':['rtl.v'],'testbench':'tb.v','defines':[],'parameters':{},'seed':None},
            'sources':[row('tb.v','testbench',evidence['checker']['testbench_source']['tb.v']),
                *[row(path,'checker',text) for path,text in evidence['checker']['adapter_source'].items()],
                row('README.md','documentation','Synthetic DUT description')],
            'logs':[{'test_id':evidence['checker']['context']['test_id'],'outcome':'functional_fail',
                     'text':evidence['checker']['plain_buggy_log']['stdout'],'snapshot_sha256':snapshot}],
            'hierarchy':evidence['graph']['instances']}
        for condition in ('C1','C2','C4','M'):
            with self.subTest(condition=condition):
                with self.assertRaisesRegex(ValueError,'Incomplete condition evidence'):
                    self.make(condition,name='strict-memory-'+condition,evidence=evidence,
                              common_context=common,raw_vcd=raw,allow_partial=False)
        directory,manifest=self.make('C4',name='partial-memory-C4',evidence=evidence,
                                    common_context=common,raw_vcd=raw,allow_partial=True)
        self.assertIs(manifest['ready'],False)
        self.assertIn('complete_buggy_trace_mapping',manifest['missing'])
        with self.assertRaisesRegex(RuntimeError,'Partial evidence'):
            export.isolation_preflight(directory,expected_manifest_sha256=export.sha((directory/'manifest.json').read_bytes()))

    def test_leaks_and_non_source_candidate_fields_are_rejected(self):
        for value in ({'case_id': 'private'}, {'operator': {'id': 'private'}},
                      '/Users/owner/rtl/buggy/dut.v', r'C:\Users\owner\secret',
                      'sha256-'+'a'*16, 'plan-'+'b'*16):
            with self.assertRaises(ValueError):
                export.leakage_check(value)
        with self.assertRaises(ValueError):
            export.leakage_check('unusual-private-token', forbidden_tokens=['unusual-private-token'])
        contaminated = copy.deepcopy(self.evidence)
        contaminated['candidates']['candidates'][0]['case_id'] = 'injected'
        with self.assertRaisesRegex(ValueError, 'Candidate inventory'):
            self.make(name='candidate-leak', evidence=contaminated)
        contaminated = copy.deepcopy(self.evidence)
        contaminated['graph']['nodes'][0]['label'] = 'injected'
        with self.assertRaisesRegex(ValueError, 'strict buggy-source'):
            self.make(name='graph-leak', evidence=contaminated)
        bad_common = copy.deepcopy(self.common)
        bad_common['logs'][0]['text'] += '\n/home/developer/private/cases/secret\n'
        with self.assertRaisesRegex(ValueError, 'audited buggy-run'):
            self.make(name='log-leak', common_context=bad_common)

    def test_partial_alignment_and_missing_common_context_block_strict_readiness(self):
        with self.assertRaisesRegex(ValueError, 'checker_signal_and_simulation_time_anchor'):
            self.make('C4', allow_partial=False)
        directory, manifest = self.make('C4')
        self.assertFalse(manifest['ready'])
        trusted = export.sha((directory/'manifest.json').read_bytes())
        with self.assertRaisesRegex(RuntimeError, 'Partial evidence'):
            export.isolation_preflight(directory, expected_manifest_sha256=trusted, backend='bubblewrap')
        bad_common = copy.deepcopy(self.common)
        bad_common['sources'].pop()
        with self.assertRaisesRegex(ValueError, 'documentation'):
            self.make(name='missing-common', common_context=bad_common)
        bad_common = copy.deepcopy(self.common)
        bad_common['logs'][0]['snapshot_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'buggy-run provenance'):
            self.make(name='wrong-log-snapshot', common_context=bad_common)

    def test_no_overwrite_inside_curator_symlinks_and_tampering(self):
        directory, _ = self.make()
        with self.assertRaisesRegex(ValueError, 'new directory'):
            self.make()
        with self.assertRaisesRegex(ValueError, 'outside the curator root'):
            export.export_evidence(self.curator/'export', evidence=self.evidence, condition='C0',
                neutral_id='sample-'+'a'*16, common_context=self.common, curator_root=self.curator,
                evidence_binding_sha256='1'*64)
        trusted = export.sha((directory/'manifest.json').read_bytes())
        (directory/'common.json').chmod(0o644)
        (directory/'common.json').write_text('{}')
        (directory/'common.json').chmod(0o444)
        with self.assertRaisesRegex(ValueError, 'sealed manifest'):
            export.verify_export(directory, expected_manifest_sha256=trusted)
        manifest = json.loads((directory/'manifest.json').read_text())
        manifest['files']['common.json'] = export.sha(b'{}')
        (directory/'manifest.json').chmod(0o644)
        (directory/'manifest.json').write_bytes(export.encoded(manifest))
        (directory/'manifest.json').chmod(0o444)
        with self.assertRaisesRegex(ValueError, 'trusted external binding'):
            export.verify_export(directory, expected_manifest_sha256=trusted)
        directory.chmod(0o755)
        (directory/'outside').symlink_to(self.curator)
        directory.chmod(0o555)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            export.verify_export(directory)

    def test_isolation_preflight_refuses_absent_or_rejected_sandbox(self):
        directory, _ = self.make()
        trusted = export.sha((directory/'manifest.json').read_bytes())
        with self.assertRaisesRegex(RuntimeError, 'trusted external'):
            export.isolation_preflight(directory, backend='bubblewrap')
        with self.assertRaisesRegex(RuntimeError, 'OS isolation backend'):
            export.isolation_preflight(directory, expected_manifest_sha256=trusted)
        with patch.object(shutil, 'which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                export.isolation_preflight(directory, expected_manifest_sha256=trusted, backend='bubblewrap')
        with patch.object(shutil, 'which', return_value='/usr/bin/bwrap'), \
             patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'AppArmor denied')) as run:
            with self.assertRaisesRegex(RuntimeError, 'AppArmor denied'):
                export.isolation_preflight(directory, expected_manifest_sha256=trusted, backend='bubblewrap')
            argv = run.call_args.args[0]
            self.assertIn('--unshare-all', argv)
            self.assertIn('--clearenv', argv)
            self.assertNotIn(str(self.curator), argv)

    def test_offline_companion_cli_writes_private_receipt_outside_export(self):
        bundle = publish_companion(self.curator/'capture', self.evidence, provenance={'case_id': 'curator-only'})
        common = self.curator/'common.json'
        common.write_bytes(export.encoded(self.common))
        destination = self.root/'cli-output'
        receipt = self.curator/'receipt.json'
        with patch('sys.argv', ['sanitized_export', '--bundle', str(bundle), '--common-context', str(common),
            '--curator-root', str(self.curator), '--output', str(destination), '--condition', 'C3',
            '--neutral-id', 'sample-'+'a'*16, '--specification', str(self.spec),
            '--specification-sha256', self.spec_hash, '--provenance-output', str(receipt)]):
            export.main()
        recorded = json.loads(receipt.read_text())
        self.assertEqual(recorded['full_specification_store_sha256'], self.spec_hash)
        manifest = export.verify_export(destination, expected_manifest_sha256=recorded['manifest_sha256'])
        self.assertEqual(recorded['public_specification_sha256'], manifest['specification_sha256'])
        self.assertNotIn('curator-only', ''.join(p.read_text() for p in destination.rglob('*') if p.is_file()))


if __name__ == '__main__':
    unittest.main()
