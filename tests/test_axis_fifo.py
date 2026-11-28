"""Checks for the fixed FIFO transcript and evidence adapters."""

from pathlib import Path
from runpy import run_path
import unittest

from rtlprobe.evidence_capture import resolve_dut_scope
from rtlprobe.evidence_observer import instrument_testbench, reset_failure_window

TARGET = Path(__file__).resolve().parents[1]/'targets/axis_fifo'
CHECKER = run_path(str(TARGET/'checker.py'))


class AxisFifoTests(unittest.TestCase):
    def test_checker_requires_a_complete_transcript_with_known_values(self):
        points = CHECKER['CHECKPOINTS']
        events = ['FIFO START v1']
        for name, (expected, _) in points.items():
            events.extend((f'FIFO BEGIN {name}', f'FIFO RESULT {name} expected={expected} actual={expected}'))
        good = '\n'.join((*events, f'FIFO END checked={len(points)} mismatches=0'))
        control = good.replace('partial_keep expected=00000001 actual=00000001',
                               'partial_keep expected=00000001 actual=00000003').replace('mismatches=0', 'mismatches=1')
        classify = CHECKER['classify']
        self.assertEqual(classify(good)['outcome'], 'pass')
        self.assertEqual(classify(control)['signature'], [dict(id='partial_keep', outcome='functional_fail',
                                                              expected='00000001', actual='00000003')])
        self.assertEqual(classify(good.split('FIFO END')[0])['outcome'], 'infrastructure_error')
        self.assertEqual(classify(good.replace('actual=00000000', 'actual=0000000x', 1))['outcome'],
                         'infrastructure_error')

    def test_fixed_dut_and_checkpoint_bindings(self):
        bench = (TARGET/'tb_axis_fifo.v').read_text()
        _, record = instrument_testbench(bench, 'axis_fifo', test_id='axis_fifo_frame_v1')
        self.assertEqual(record['sampling_sites'], list(CHECKER['CHECKPOINTS']))
        self.assertEqual(record['window_start_sites'], record['sampling_sites'])
        with self.assertRaisesRegex(ValueError, 'sampling sites'):
            instrument_testbench(bench.replace('begin_check("partial_keep");', ''), 'axis_fifo',
                                 test_id='axis_fifo_frame_v1')
        args = dict(top='axis_fifo', test_top='tb_axis_fifo')
        self.assertEqual(resolve_dut_scope(bench, **args, fixed_parameters=True), 'tb_axis_fifo.dut')
        with self.assertRaisesRegex(ValueError, 'unparameterized'):
            resolve_dut_scope(bench, **args)
        with self.assertRaisesRegex(ValueError, 'literal named'):
            resolve_dut_scope(bench.replace('.DEPTH(16)', '.DEPTH(WIDTH)'), **args, fixed_parameters=True)

    def test_active_high_reset_window(self):
        trace = {'signals': [{'normalized_reference':'tb_axis_fifo.dut.rst',
                              'events':[[0,'0'], [10,'1'], [30,'0']]}]}
        reset, window = reset_failure_window(trace, [{'outcome':'functional_fail','tick':50}],
                                              dut_scope='tb_axis_fifo.dut', target_id='axis_fifo')
        self.assertEqual((reset['asserted_tick'], reset['released_tick']), (10,30))
        self.assertEqual((window['start_tick'], window['end_tick']), (10,50))
