"""Exercise the AES suite and capture contract using a synthetic core."""

from pathlib import Path
import re
import runpy
import shutil
import subprocess
import tempfile
import unittest

from rtlprobe import pilot, target
from rtlprobe.capture_execution import seal_capture_execution
from rtlprobe.evidence import CODE_ROOT, filehash
from rtlprobe.evidence_capture import capture_observation, load_inference_evidence
from rtlprobe.oracle import classify
from rtlprobe.sanitized_export import public_checker, waveform_views


SUITE = CODE_ROOT/'targets/aes/extended'
CONFIG = target.configuration(SUITE/'config.json')
BENCH = pilot.input_path(CONFIG, CONFIG['testbench'])
EXPECTED = runpy.run_path(str(SUITE/'checker.py'))['EXPECTED']
ASSERTION_CONFIG = target.configuration(CODE_ROOT/'targets/aes/extended_v2/config.json')

MOCK = '''
module aes_core(input clk, reset_n, encdec, init, next,
                output reg ready, input [255:0] key, input keylen,
                input [127:0] block, output reg [127:0] result, output reg result_valid);
  reg [255:0] active_key;
  reg [127:0] pending;
  reg pending_block;
  reg [2:0] remaining;
  reg used_key;
  reg saw_reset;
  initial saw_reset = 0;

  always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
      ready <= 1;
      result_valid <= 0;
      result <= 0;
      remaining <= 0;
      active_key <= 0;
      used_key <= 0;
      pending <= 0;
      pending_block <= 0;
    end else if (init && ready) begin
      active_key <= keylen ? key : {key[255:128], 128'b0};
      ready <= 0;
      result_valid <= 0;
      remaining <= 4;
      pending_block <= 0;
      used_key <= 0;
    end else if (next && ready) begin
      case ({active_key, encdec, block})
        CASES
        default: pending <= 0;
      endcase
      ready <= 0;
      result_valid <= 0;
      remaining <= 4;
      pending_block <= 1;
    end else if (!ready && remaining != 0) begin
`ifndef STALL
      remaining <= remaining - 1;
`endif
      if (remaining == 1) begin
        ready <= 1;
        result_valid <= pending_block;
        if (pending_block) begin
`ifdef BAD_REUSE
          result <= used_key && !encdec ? (pending ^ 128'b1) : pending;
`else
          result <= pending;
`endif
          used_key <= 1;
        end
      end
    end
  end

`ifdef STALE_VALID
  always @(posedge reset_n) begin
    if (saw_reset)
      result_valid <= 1;
    saw_reset <= 1;
  end
`endif
endmodule
'''


def independent_lookup():
    bench = BENCH.read_text()
    blocks = dict(re.findall(r"localparam \[127:0\] (\w+) = 128'h([0-9a-f]{32});", bench))
    keys = dict(re.findall(r"localparam \[255:0\] (\w+) = .*?'h([0-9a-f]+)", bench))
    commands = re.finditer(r'start_init\(AES(128|256), (\w+)\);|'
                           r'check_block\("(\w+)", (ENCRYPT|DECRYPT), (\w+), (\w+)\);', bench)
    table, comparisons = {}, {}
    for command in commands:
        width, key_name, name, mode, data, expected = command.groups()
        if width:
            bits, key = width, keys[key_name]
            continue
        decrypt = mode == 'DECRYPT'
        actual = subprocess.run(['openssl', 'enc', f'-aes-{bits}-ecb', '-nopad', '-K', key,
                                 '-d' if decrypt else '-e'], input=bytes.fromhex(blocks[data]),
                                capture_output=True, check=True, timeout=5).stdout.hex()
        table[key.ljust(64, '0') + ('0' if decrypt else '1') + blocks[data]] = actual
        comparisons[name] = (blocks[expected], actual)
    return table, comparisons


class AESExtendedTests(unittest.TestCase):
    def test_checker_rejects_inconsistent_or_incomplete_transcripts(self):
        lines = ['AES_EXT START v1']
        for name, expected in EXPECTED.items():
            lines.extend([f'AES_EXT BEGIN {name}', f'AES_EXT RESULT {name} expected={expected} actual={expected}'])
        lines.append(f'AES_EXT END checked={len(EXPECTED)} mismatches=0')
        valid = '\n'.join(lines)
        self.assertEqual(classify(valid, config=CONFIG)['outcome'], 'pass')
        for bad in (lines[:-1], [*lines, lines[-1]], [*lines[:2], *lines[4:]],
                    [*lines[:2], lines[2][:-1] + 'X', *lines[3:]]):
            self.assertEqual(classify('\n'.join(bad), config=CONFIG)['outcome'], 'infrastructure_error')

    def test_terminal_assertions_require_the_checkpoint_signature_and_exact_end_record(self):
        first = next(iter(EXPECTED))
        terminal = f'AES_EXT TERMINAL {first} after_reset ready expected=1 actual=0'
        lines = ['AES_EXT START v2', f'AES_EXT BEGIN {first}', terminal, 'AES_EXT STOP checked=0 mismatches=0']
        valid = '\n'.join(lines)
        result = classify(valid, config=ASSERTION_CONFIG)
        self.assertTrue(result['terminal_failure'])
        self.assertEqual([check['id'] for check in result['signature']], [first])
        self.assertEqual(result['signature'][0]['failure_kind'], 'protocol')
        for bad in (lines[:-1], [*lines, lines[-1]],
                    [*lines[:2], terminal.replace('expected=1', 'expected=0'), lines[-1]],
                    [*lines[:2], terminal.replace(first, 'reset_during_block'), lines[-1]]):
            self.assertEqual(classify('\n'.join(bad), config=ASSERTION_CONFIG)['outcome'], 'infrastructure_error')
        self.assertEqual(classify(valid, timed_out=True, config=ASSERTION_CONFIG)['reason'], 'wall_clock_timeout')

    @unittest.skipUnless(shutil.which('openssl') and shutil.which('iverilog') and shutil.which('vvp'),
                         'requires OpenSSL and Icarus')
    def test_assertion_waveforms_match_protocol_cycle_limit_and_unknown_result(self):
        table, _ = independent_lookup()
        core = MOCK.replace('CASES', '\n        '.join(
            f"{{256'h{key_block[:64]}, 1'b{key_block[64]}, 128'h{key_block[65:]}}}: pending <= 128'h{value};"
            for key_block, value in table.items()))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'source'
            source.mkdir()
            bench = pilot.input_path(ASSERTION_CONFIG, ASSERTION_CONFIG['testbench'])
            tb_path = source/'tb.v'
            shutil.copyfile(bench, tb_path)
            config = {**ASSERTION_CONFIG, 'rtl':['core.v'], 'testbench':'tb.v'}
            for mode, kind, port in (('STALL','transaction_cycle_limit','ready'),
                                     ('STALE_VALID','protocol','result_valid'),
                                     ('UNKNOWN','unknown_block_result','result')):
                with self.subTest(mode=mode):
                    core_path = source/'core.v'
                    core_path.write_text(core.replace('result <= pending;', "result <= 128'bx;") if mode == 'UNKNOWN' else core)
                    selected = {**config, 'compile_flags':['-g2005', '-D'+mode]}
                    hashes = {path.name:filehash(path) for path in (core_path,tb_path)}
                    output = root/mode
                    companion = capture_observation(config=selected, buggy_root=source, destination=output,
                                                    expected_hashes=hashes, execution_guard=lambda: True)
                    evidence = load_inference_evidence(companion)
                    checker = evidence['checker']
                    failure = checker['verdict']['signature'][0]
                    self.assertEqual(failure['failure_kind'], kind)
                    anchor = next(row for row in checker['anchors'] if row['checkpoint'] == failure['id'])
                    self.assertEqual(anchor['signal'], 'tb_aes_extended.dut.'+port)
                    self.assertEqual(anchor['value_match'], 'matched')
                    self.assertEqual([row['checkpoint'] for row in checker['anchors']],
                                     [row['id'] for row in checker['verdict']['checkpoints']])
                    projection = public_checker(checker)
                    self.assertEqual(projection['verdict'], checker['verdict'])
                    self.assertNotIn('anchors', projection)
                    self.assertIsNotNone(waveform_views(evidence))
                    seal_capture_execution(output, config=selected, expected_hashes=hashes)

    @unittest.skipUnless(shutil.which('openssl') and shutil.which('iverilog') and shutil.which('vvp'),
                         'requires OpenSSL and Icarus')
    def test_vectors_transcript_and_waveform_with_synthetic_core(self):
        table, comparisons = independent_lookup()
        self.assertEqual(list(comparisons), list(EXPECTED))
        self.assertEqual(comparisons, {name: (value, value) for name, value in EXPECTED.items()})
        core = MOCK.replace('CASES', '\n        '.join(
            f"{{256'h{key_block[:64]}, 1'b{key_block[64]}, 128'h{key_block[65:]}}}: pending <= 128'h{value};"
            for key_block, value in table.items()))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'source'
            source.mkdir()
            core_path = source/'core.v'
            tb_path = source/'tb.v'
            core_path.write_text(core)
            shutil.copyfile(BENCH, tb_path)
            for define, outcome, reason in (
                ('NOMINAL', 'pass', 'checker_completed'),
                ('STALL', 'timeout_unclassified', 'transaction_cycle_limit'),
                ('STALE_VALID', 'infrastructure_error', 'protocol_after_reset'),
            ):
                with self.subTest(define=define):
                    binary = root/(define+'.vvp')
                    subprocess.run(['iverilog', '-g2005', '-D'+define, '-s', CONFIG['test_top'], '-o', binary,
                                    core_path, tb_path], cwd=root, capture_output=True, check=True, timeout=10)
                    run = subprocess.run(['vvp', '-N', binary], cwd=root, capture_output=True, text=True,
                                         check=True, timeout=5)
                    result = classify(run.stdout, run.stderr, config=CONFIG)
                    self.assertEqual((result['outcome'], result['reason']), (outcome, reason), run.stdout)

            config = {**CONFIG, 'rtl': ['core.v'], 'testbench': 'tb.v', 'compile_flags': ['-g2005', '-DBAD_REUSE']}
            hashes = {path.name: filehash(path) for path in (core_path, tb_path)}
            output = root/'capture'
            companion = capture_observation(config=config, buggy_root=source, destination=output,
                                            expected_hashes=hashes, execution_guard=lambda: True)
            value = load_inference_evidence(companion)['checker']
            self.assertEqual(value['observational_parity'], 'matched')
            self.assertEqual([a['checkpoint'] for a in value['anchors']], list(EXPECTED))
            self.assertEqual([w['checkpoint'] for w in value['test_windows']], list(EXPECTED))
            self.assertEqual([row['id'] for row in value['verdict']['signature']],
                             ['key128_reuse_decrypt', 'key128_reuse_decrypt_again', 'key256_reuse_decrypt'])
            seal_capture_execution(output, config=config, expected_hashes=hashes)
