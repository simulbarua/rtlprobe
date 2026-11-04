"""Synthetic source/VCD/log and mocked Runner tests; never executes HDL tools."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rtlprobe.evidence import CODE_ROOT, filehash
from rtlprobe.evidence_capture import (build_inference_evidence, validate_inference_evidence,
    publish_companion, load_inference_evidence, capture_observation, source_hashes)
from rtlprobe.evidence_structure import build_structure, observer_source
from rtlprobe.evidence_observer import instrument_testbench, compiled_timebase

PASS = """-- Testbench for sha256 core started --
*** TC 1 single block test case started.
*** TC 1 successful.
*** TC 2 double block test case started.
*** TC 2 first block successful
*** TC 2 second block successful
Running test for 9 block issue.
Digest ok.
*** All 03 test cases completed successfully
*** Simulation done.
"""
FAIL = PASS.replace('*** TC 1 successful.', '*** ERROR: TC 1 NOT successful.\nExpected: 0x'+'a'*64+'\nGot:      0x'+'b'*64).replace('All 03 test cases completed successfully', '01 test cases did not complete successfully.')
POINTS = ['tc1','tc2_block1','tc2_block2','issue9']
SOURCE = """module m(input wire reset_n, output wire [255:0] digest);
  reg [31:0] mem [0:1];
  assign digest = 256'hbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb;
  always @* begin : update
    mem[0] = 32'h0;
    mem[1] = 32'h1;
  end
endmodule
"""
TB = """module tb;
wire tb_reset_n; wire [255:0] tb_digest;
m dut(.reset_n(tb_reset_n), .digest(tb_digest));
task single_block_test; reg [255:0] expected; begin
 if (tb_digest == expected) begin end
end endtask
task double_block_test; reg [255:0] db_digest1, db_digest2, expected1, expected2; begin
 db_digest1 = tb_digest;
 db_digest2 = tb_digest;
 if (db_digest1 == expected1) begin end
 if (db_digest2 == expected2) begin end
end endtask
task issue_test; reg [255:0] expected; begin
 if (tb_digest == expected) begin end
end endtask
endmodule
"""


def waveform(missing_word=False, outside=False):
    lines = ['$timescale 1 ns $end', '$scope module tb $end', '$scope module dut $end',
        '$var wire 1 ! reset_n $end', '$var wire 256 " digest [255:0] $end',
        '$var reg 32 # \\mem[0] [31:0] $end']
    if not missing_word:
        lines.append('$var reg 32 $ \\mem[1] [31:0] $end')
    lines += ['$upscope $end']
    if outside:
        lines += ['$var reg 1 % hidden_expected $end']
    lines += ['$upscope $end', '$enddefinitions $end', '#0', '0!', 'b'+'1011'*64+' "', 'b0 #']
    if not missing_word:
        lines.append('b1 $')
    lines += ['#1', '1!', '#2', '#3', '#4', '#5', '#6', 'b'+'1100'*64+' "', '']
    return '\n'.join(lines)


def observed_log():
    lines = ['VCD info: dumpfile buggy.vcd opened for output.']
    for number, point in enumerate(POINTS):
        start, end = (0 if number == 0 else number+1), number+2
        expected = ('a' if number == 0 else 'b')*64
        lines += [f'RTLPROBE_WINDOW checkpoint={point} start_units={start}',
                  f'RTLPROBE_OBSERVE checkpoint={point} time_units={end} expected={expected} actual='+('b'*64)]
    return '\n'.join(lines)+'\n'+FAIL


def fixture(**changes):
    values = dict(buggy_sources={'rtl.v':SOURCE}, top='m', dut_scope='tb.dut', raw_vcd=waveform(),
        checker_context={'target_id':'sha256','test_id':'upstream_core_all','checkpoints':POINTS},
        testbench_source={'tb.v':TB},
        plain_buggy_log={'stdout':FAIL,'stderr':'','returncode':0,'timed_out':False},
        observed_buggy_log={'stdout':observed_log(),'stderr':'','returncode':0,'timed_out':False},
        timebase=compiled_timebase('.scope module, "tb" "tb";\n .timescale -9 -9;\n','tb'))
    values.update(changes)
    return build_inference_evidence(**values)


class EvidenceCaptureTests(unittest.TestCase):
    def test_full_raw_retention_time_binding_and_signature_parity(self):
        payload=fixture()
        self.assertIs(validate_inference_evidence(payload),payload)
        self.assertEqual(payload['trace']['raw_vcd'],waveform())
        self.assertEqual(payload['trace']['analysis_window']['end_tick'],2)
        self.assertEqual([(w['start_tick'],w['end_tick']) for w in payload['trace']['passing_test_windows']],[(2,3),(3,4),(4,5)])
        self.assertEqual(payload['trace']['capture_end_tick'],6)
        self.assertEqual(payload['checker']['observational_parity'],'matched')
        self.assertEqual(payload['checker']['anchors'][0]['signal'],'tb.dut.digest')
        self.assertEqual(payload['trace']['reset']['released_tick'],1)
        self.assertEqual(payload['trace']['status'],'complete')

    def test_memory_omission_and_missing_timebase_are_explicit(self):
        missing=fixture(raw_vcd=waveform(missing_word=True))
        self.assertEqual(missing['trace']['missing_signals'],['tb.dut.mem[1]'])
        self.assertEqual(missing['trace']['status'],'partial')
        missing=fixture(timebase=None)
        self.assertEqual(missing['checker']['anchor_status'],'unavailable')
        self.assertIsNone(missing['trace']['analysis_window'])
        self.assertEqual(missing['trace']['status'],'partial')
        observer,policy=observer_source(missing['graph'])
        self.assertIn('$dumpvars(0, tb.dut.mem[0]);',observer)
        self.assertIn('$dumpvars(0, tb.dut.mem[1]);',observer)
        self.assertNotIn('$finish',observer)
        self.assertEqual(policy['explicit_memory_words'],2)

    def test_unsupported_memory_shapes_and_large_ranges_stay_partial_without_expansion(self):
        raw='\n'.join(line for line in waveform(missing_word=True).splitlines()
                      if not line.startswith('$var reg 32 #') and line!='b0 #')+'\n'
        variants=[('mem [0:1][0:1]','only one static unpacked dimension supported'),
                  ('mem [0:1000000000000]','explicit memory dump word budget exceeded')]
        for declaration,reason in variants:
            with self.subTest(declaration=declaration):
                source=SOURCE.replace('mem [0:1]',declaration)
                if '][0:1]' in declaration:
                    source=source.replace('mem[0] =','mem[0][0] =').replace('mem[1] =','mem[1][1] =')
                payload=fixture(buggy_sources={'rtl.v':source},raw_vcd=raw)
                self.assertEqual({k:payload[k]['status'] for k in ('graph','alignment','trace')},
                                 dict.fromkeys(('graph','alignment','trace'),'partial'))
                node=next(n for n in payload['graph']['nodes'] if n['signal']=='tb.dut.mem')
                self.assertIn(reason,node['missingness'])
                self.assertEqual(payload['trace']['missing_signals'],['tb.dut.mem'])
                self.assertEqual(payload['trace']['unavailable_signals'],[{'signal':'tb.dut.mem','reason':reason}])
                observer,policy=observer_source(payload['graph'])
                self.assertEqual(policy['missingness'],[{'signal':'tb.dut.mem','reason':reason}])
                self.assertEqual(policy['explicit_memory_words'],0)
                self.assertNotIn('$dumpvars(0, tb.dut.mem[',observer)
                with tempfile.TemporaryDirectory() as tmp:
                    output=publish_companion(Path(tmp)/'partial',payload,provenance={'synthetic':True})
                    self.assertEqual(load_inference_evidence(output),payload)

    def test_outside_scope_time_value_and_semantic_mismatch_refused(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            fixture(raw_vcd=waveform(outside=True))
        changed={'stdout':observed_log().replace('time_units=2','time_units=20'), 'stderr':'','returncode':0,'timed_out':False}
        with self.assertRaisesRegex(ValueError,'align'):
            fixture(observed_buggy_log=changed)
        with self.assertRaisesRegex(ValueError,'coarser'):
            fixture(timebase=compiled_timebase('.scope module, "tb" "tb";\n .timescale -9 -12;','tb'))
        changed={'stdout':observed_log().replace('actual='+'b'*64,'actual='+'c'*64,1),'stderr':'','returncode':0,'timed_out':False}
        with self.assertRaisesRegex(ValueError,'waveform'):
            fixture(observed_buggy_log=changed)
        changed={'stdout':observed_log().replace('*** TC 2 first block successful','BROKEN'),'stderr':'','returncode':0,'timed_out':False}
        with self.assertRaisesRegex(ValueError,'semantics'):
            fixture(observed_buggy_log=changed)
        diagnostic='VCD warning: array word tb.dut.mem[0] will conflict with an escaped identifier.\n'
        known={'stdout':diagnostic+observed_log(),'stderr':'','returncode':0,'timed_out':False}
        self.assertEqual(fixture(observed_buggy_log=known)['checker']['observational_parity'],'matched')
        unknown={**known,'stdout':known['stdout'].replace('mem[0]','mem[99]')}
        with self.assertRaisesRegex(ValueError,'semantics'):
            fixture(observed_buggy_log=unknown)

    def test_companion_immutable_and_curator_fields_never_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'new'; payload=fixture()
            publish_companion(out,payload,provenance={'case_id':'secret','operator':'secret','label':123})
            self.assertEqual(load_inference_evidence(out),payload)
            self.assertNotIn('secret',json.dumps(load_inference_evidence(out)))
            with self.assertRaises(ValueError):publish_companion(out,payload,provenance={})
            (out/'extra.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'unexpected'):load_inference_evidence(out)
            (out/'extra.json').unlink()
            value=json.loads((out/'inference.json').read_text()); value['graph']['label']='secret'
            (out/'inference.json').write_text(json.dumps(value))
            manifest=json.loads((out/'manifest.json').read_text());manifest['files']['inference.json']=filehash(out/'inference.json')
            (out/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'rederivation'):load_inference_evidence(out)

    def test_named_ports_locals_pure_functions_and_unsupported_effects(self):
        source='''module child(input wire a, output wire y); assign y=a; endmodule
module m(input wire [31:0] a, output wire [31:0] y);
function [31:0] l2b(input [31:0] op); begin
l2b = {op[7:0], op[15:8], op[23:16], op[31:24]};
end endfunction
reg [31:0] q;
always @* begin : local_scope
reg [31:0] t;
t=l2b(a);
q=t;
end
assign y=q;
endmodule'''
        graph,alignment=build_structure({'m.v':source},top='m',dut_scope='tb.dut')
        self.assertEqual(graph['status'],'complete')
        self.assertIn('tb.dut.local_scope.t',[n['signal'] for n in graph['nodes']])
        function_mapping=[m for m in alignment['mappings'] if m['line']==4]
        self.assertTrue(function_mapping and function_mapping[0]['signals'])
        self.assertEqual(graph['functions'][0]['status'],'supported_pure_static')
        bad=source.replace('op[7:0]','q[7:0]')
        graph,_=build_structure({'m.v':bad},top='m',dut_scope='tb.dut')
        self.assertEqual(graph['status'],'partial')
        graph,_=build_structure({'c.v':'module c(input wire a,output wire y);assign y=a;endmodule',
          'm.v':'module m(input wire a,output wire y);c u(.a(a),.y(y));endmodule'},top='m',dut_scope='tb.dut')
        self.assertIn({'source':'tb.dut.a','target':'tb.dut.u.a','kind':'port','path':'m.v','line':1},graph['edges'])
        unsafe={'nodes':[{'signal':'tb.dut.bad); $finish; //','unpacked_ranges':[]}],
                'context':{'dut_scope':'tb.dut'}}
        with self.assertRaisesRegex(ValueError,'safe'):
            observer_source(unsafe)

    def test_observation_transform_is_additive_and_requires_exact_sites(self):
        changed,policy=instrument_testbench(TB,'sha256')
        self.assertEqual(policy['sampling_sites'],POINTS)
        # Delete only generated observation statements; existing source remains as
        # byte substrings in the same order and no expected/stimulus write is added.
        self.assertIn('db_digest1 = tb_digest;',changed)
        self.assertIn('if (tb_digest == expected)',changed)
        self.assertEqual(changed.count('RTLPROBE_OBSERVE'),4)
        with self.assertRaisesRegex(ValueError,'sampling sites'):
            instrument_testbench(TB.replace('db_digest1 = tb_digest;','db_digest1 = 0;'),'sha256')
        with self.assertRaisesRegex(ValueError,'direct task block'):
            instrument_testbench(TB.replace('if (tb_digest == expected)','if (1) if (tb_digest == expected)'),'sha256')
        with self.assertRaises(ValueError):compiled_timebase('.timescale -9 -9;','tb')

    def test_chacha_repeated_labels_use_checked_invocation_ordinals(self):
        from test_chacha_checker import CASES, transcript
        source='module core(input wire reset_n, output reg [511:0] data_out); endmodule'
        tb='''module tb;
wire reset_n; wire [511:0] tb_core_data_out;
core dut(.reset_n(reset_n),.data_out(tb_core_data_out));
task run_test_case; reg [511:0] expected; begin
if (tb_core_data_out == expected) begin end
end endtask
endmodule'''
        instrumented,policy=instrument_testbench(tb,'chacha')
        self.assertIn('rtlprobe_observer.comparison_ordinal + 1',instrumented)
        self.assertEqual(policy['sampling_sites'],['ordered_core_comparison'])
        plain=transcript((7,));messages=[]
        vcd=['$timescale 1 ns $end','$scope module tb $end','$scope module dut $end',
             '$var wire 1 ! reset_n $end','$var reg 512 " data_out [511:0] $end',
             '$upscope $end','$upscope $end','$enddefinitions $end','#0','0!','b0 "','#1','1!']
        for index,case in enumerate(CASES):
            tick=(index+1)*2;actual=format(int(case['expected'],16)^(index==7),'0128x')
            messages += [f'RTLPROBE_WINDOW ordinal={index+1} start_units={tick-1}',
                f'RTLPROBE_OBSERVE ordinal={index+1} time_units={tick} expected={case["expected"]} actual={actual}']
            vcd += [f'#{tick}','b'+format(int(actual,16),'0512b')+' "']
        logs={'stdout':plain,'stderr':'','returncode':0,'timed_out':False}
        payload=build_inference_evidence(buggy_sources={'core.v':source},top='core',dut_scope='tb.dut',
            raw_vcd='\n'.join(vcd)+'\n',checker_context={'target_id':'chacha','test_id':'suite',
                'checkpoints':[c['id'] for c in CASES]},testbench_source={'tb.v':tb},
            plain_buggy_log=logs,observed_buggy_log={**logs,'stdout':'\n'.join(messages)+'\n'+plain},
            timebase=compiled_timebase('.scope module, "tb" "tb";\n .timescale -9 -9;','tb'))
        self.assertEqual(payload['trace']['analysis_window']['end_tick'],16)
        self.assertEqual(payload['checker']['anchors'][7]['checkpoint'],'case08_tc2_1')
        self.assertEqual(payload['trace']['status'],'complete')

    def test_noop_or_revoked_guard_prevents_execution_and_case_writes(self):
        for guard in (None,lambda:None,lambda:False):
            with tempfile.TemporaryDirectory() as tmp:
                destination=Path(tmp)/'out'
                with self.assertRaises(PermissionError):
                    capture_observation(config={},buggy_root=tmp,destination=destination,expected_hashes={},execution_guard=guard)
                self.assertFalse(destination.exists())
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'sealed';case.mkdir();(case/'manifest.json').write_text('{"sealed":true}')
            before=(case/'manifest.json').read_bytes()
            with self.assertRaisesRegex(ValueError,'sealed'):
                capture_observation(config={'target_id':'sha256'},buggy_root=Path(tmp)/'source',
                    destination=case/'new',expected_hashes={},execution_guard=lambda:True)
            self.assertEqual((case/'manifest.json').read_bytes(),before)
            self.assertFalse((case/'new').exists())

    def test_bounded_capture_uses_mocked_runner_only_and_preserves_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';root.mkdir();(root/'rtl.v').write_text(SOURCE);(root/'tb.v').write_text(TB)
            before={p:filehash(root/p) for p in ('rtl.v','tb.v')};output=Path(tmp)/'capture'; calls=[]
            class FakeRunner:
                def __init__(self,out,limits):self.out=out
                def require(self,name,command,cwd,timeout):
                    calls.append((name,command,timeout));binary=Path(command[command.index('-o')+1]);binary.write_text('.scope module, "tb" "tb";\n .timescale -9 -9;\n')
                    return {'id':name,'command':command,'returncode':0,'timed_out':False}
                def run(self,name,command,cwd,timeout):
                    calls.append((name,command,timeout));observed=name.startswith('observed')
                    if observed:(cwd/'buggy.vcd').write_text(waveform())
                    out=self.out/(name+'.stdout');err=self.out/(name+'.stderr');out.write_text(observed_log() if observed else FAIL);err.write_text('')
                    return {'id':name,'command':command,'returncode':0,'timed_out':False,'stdout':out.name,'stderr':err.name}
            config={'target_id':'sha256','top':'m','test_top':'tb','test_id':'upstream_core_all',
                'rtl':['rtl.v'],'testbench':'tb.v','compile_flags':['-g2005'],
                'test_metadata':{'checkpoints':POINTS},'limits':{'compile_seconds':3,'simulation_seconds':2}}
            with patch('subprocess.Popen',side_effect=AssertionError('native execution forbidden')):
                companion=capture_observation(config=config,buggy_root=root,destination=output,expected_hashes=before,
                    execution_guard=lambda:True,runner_factory=FakeRunner)
            self.assertEqual(len(calls),4)
            self.assertEqual(before,{p:filehash(root/p) for p in before})
            self.assertTrue(all(c[2] in {2,3} for c in calls))
            self.assertTrue(all(c[1][-3:-1]==['vvp','-N'] for c in calls if c[0].endswith('_run')))
            self.assertEqual(load_inference_evidence(companion)['trace']['status'],'complete')
            self.assertFalse((root/'manifest.json').exists())
            checks=iter([True]*9+[None])
            with self.assertRaises(PermissionError):
                capture_observation(config=config,buggy_root=root,destination=Path(tmp)/'revoked',expected_hashes=before,
                    execution_guard=lambda:next(checks),runner_factory=FakeRunner)
            self.assertFalse((Path(tmp)/'revoked/companion').exists())


if __name__=='__main__':unittest.main()
