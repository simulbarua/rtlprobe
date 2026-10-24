"""Ensure repository selection is explicit and checker behavior is isolated."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from rtlprobe import target
from rtlprobe.evidence import CODE_ROOT, load
from rtlprobe.oracle import classify
from rtlprobe.oracle import historical_checker


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.config = load(CODE_ROOT/'targets/sha256/config.json')

    def test_no_implicit_target_even_with_inherited_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, RTLPROBE_TARGET_CONFIG=str(CODE_ROOT/'targets/sha256/config.json'))
            result = subprocess.run([sys.executable, str(CODE_ROOT/'scripts/rtlprobe.py'), '--data-root', tmp, 'check'], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('explicit --target-config', result.stderr)
            self.assertNotIn('Traceback', result.stderr)

    def test_namespace_can_be_an_unrelated_target(self):
        config = copy.deepcopy(self.config)
        config.update(target_id='different_core', case_prefix='different', split_group='other_lineage')
        self.assertEqual(target.validate(config)['target_id'], 'different_core')
        self.assertEqual(target.design_directory(config).name, 'different_core')

    def test_unsafe_or_incomplete_manifests_fail(self):
        for changes in [dict(target_id='../escape'), dict(case_prefix='a/b'), dict(revision='main'),
                        dict(checker={'path':'../oracle.py'}), dict(compile_flags='-g2005'),
                        dict(defines=['UNIMPLEMENTED']), dict(test_metadata={'checkpoints':[]}),
                        dict(top='top; exec command')]:
            with self.subTest(changes=changes), self.assertRaises((ValueError, KeyError)):
                target.validate(dict(self.config, **changes))

    def test_checker_is_explicit_not_detected_from_repository(self):
        config = dict(self.config, checker={'path':'tests/fixtures/tiny_checker.py'}, test_metadata={'checkpoints':['sum']})
        self.assertEqual(classify('BEGIN\nCHECK PASS\nSUMMARY errors=0\nEND\n', config=config)['outcome'], 'pass')
        self.assertEqual(classify('BEGIN\nCHECK PASS\nSUMMARY errors=0\n', config=config)['outcome'], 'infrastructure_error')
        with self.assertRaises(ValueError):
            classify('anything', config={})

    def test_checker_cannot_omit_declared_checkpoints(self):
        config = dict(self.config, checker={'path':'tests/fixtures/tiny_checker.py'})
        with self.assertRaisesRegex(ValueError, 'checkpoints'):
            classify('BEGIN\nCHECK PASS\nSUMMARY errors=0\nEND\n', config=config)

    def test_checker_code_changes_fingerprint(self):
        from rtlprobe import pilot
        with tempfile.TemporaryDirectory(dir=CODE_ROOT/'tests') as tmp:
            adapter = Path(tmp)/'checker.py'; adapter.write_text('def classify(*args): pass\n')
            config = dict(self.config, checker={'path':str(adapter.relative_to(CODE_ROOT))})
            with patch.object(pilot, 'inputs', return_value={}), patch.object(pilot, 'environment', return_value={}):
                before = pilot.fingerprint(config)
                adapter.write_text('def classify(*args): return {}\n')
                self.assertNotEqual(before['sha256'], pilot.fingerprint(config)['sha256'])

    def test_earliest_evidence_requires_explicit_compatibility_selection(self):
        legacy = {k:v for k,v in self.config.items() if k not in ('checker','test_metadata')}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'explicit compatibility'):
                historical_checker(legacy, tmp)
            selected, root, mode = historical_checker(legacy, tmp, self.config)
            self.assertEqual(mode, 'explicit_compatibility_reparse')
            self.assertEqual(root, CODE_ROOT)
            self.assertEqual(selected['checker'], self.config['checker'])
            with self.assertRaisesRegex(ValueError, 'does not match'):
                historical_checker(legacy, tmp, dict(self.config, repository_url='different'))

    def test_frozen_checker_takes_precedence_over_explicit_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'rtlprobe').mkdir(); (root/'rtlprobe/oracle.py').write_text('# frozen')
            selected, actual, mode = historical_checker({}, root, self.config)
            self.assertEqual((selected, actual, mode), ({}, root, 'frozen_checker'))


if __name__ == '__main__':
    unittest.main()
