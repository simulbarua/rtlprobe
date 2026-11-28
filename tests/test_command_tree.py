"""Recovery proof checks and harmless live commands in temporary workspaces."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from unittest.mock import patch

from rtlprobe import command_tree, evidence
from rtlprobe.evidence import Runner, save, workspace_lock
from rtlprobe.lifecycle import reserve_attempt


class CommandTreeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.out = self.root/'first'
        with workspace_lock(self.root):
            reserve_attempt(self.root, 'key', 'fp', lambda: self.out)
        self.directory = self.out/'commands'/'fixture'

    def test_legacy_start_without_pid_stays_blocked(self):
        save(self.directory/'started.json', {'id': 'fixture'})
        with workspace_lock(self.root), self.assertRaisesRegex(RuntimeError, 'never recorded'):
            reserve_attempt(self.root, 'key', 'fp', lambda: self.fail('Allocated before exit'))

    def test_knowledge_of_start_record_is_insufficient_for_clearance(self):
        start = self.directory/'started.json'
        save(start, dict(tree_launch_id=hashlib.sha256(os.urandom(32)).hexdigest()))
        save(self.directory/'tree-exited.json', dict(schema='rtlprobe-subreaper-exit-1', returncode=0,
             command_directory=str(self.directory), start_sha256=hashlib.sha256(start.read_bytes()).hexdigest(),
             exit_key='0'*64))
        with workspace_lock(self.root), self.assertRaisesRegex(RuntimeError, 'unverified'):
            reserve_attempt(self.root, 'key', 'fp', lambda: self.fail('Accepted fabricated evidence'))

    @unittest.skipUnless(sys.platform=='linux', 'requires Linux subreaper support')
    def test_exit_status_streams_and_native_pid_are_preserved(self):
        runner = Runner(self.out, dict(campaign_seconds=15,cpu_seconds=15,disk_bytes=200000), supervise_tree=True)
        code = "import os,sys;print(os.getpid());print('fixture',file=sys.stderr);sys.exit(7)"
        result = runner.run('fixture', [sys.executable, '-c', code], self.root, 5)
        self.assertEqual(result['returncode'], 7)
        self.assertEqual((self.directory/'stderr.log').read_text().strip(), 'fixture')
        pid = int((self.directory/'stdout.log').read_text())
        receipt = json.loads((self.directory/'process.json').read_bytes())
        self.assertEqual(receipt['pid'], pid)
        self.assertNotEqual(receipt['group_id'], pid)
        self.assertEqual(command_tree.exit_receipt(self.directory)[0], 7)

    @unittest.skipUnless(sys.platform=='linux', 'requires Linux subreaper support')
    def test_pid_write_error_leaves_reconcilable_exit_proof(self):
        runner = Runner(self.out, dict(campaign_seconds=10,cpu_seconds=10,disk_bytes=200000), supervise_tree=True)
        def fail_pid(path, value):
            if path.name == 'process.json':
                raise OSError('PID receipt unavailable')
            save(path, value)
        with patch.object(evidence, 'save', fail_pid), self.assertRaisesRegex(OSError, 'PID receipt unavailable'):
            runner.run('fixture', [sys.executable, '-c', 'import time;time.sleep(8)'], self.root, 5)
        with workspace_lock(self.root):
            state, _, _ = reserve_attempt(self.root, 'key', 'fp', lambda: self.root/'second')
        self.assertEqual([row['status'] for row in state['attempts']], ['interrupted', 'running'])

    @unittest.skipUnless(sys.platform=='linux', 'requires Linux subreaper support')
    def test_timeout_reaps_worker_and_detached_child(self):
        runner = Runner(self.out, dict(campaign_seconds=10,cpu_seconds=10,disk_bytes=200000), supervise_tree=True)
        code = ("import os,signal,time\n"
                "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
                "if not os.fork():\n"
                "    os.setsid()\n"
                "    print(os.getpid(),flush=True)\n"
                "time.sleep(8)")
        result = runner.run('fixture', [sys.executable, '-c', code], self.root, 1)
        child_pid = (self.directory/'stdout.log').read_text().strip()
        self.assertTrue(child_pid.isdigit())
        self.assertFalse((Path('/proc')/child_pid).exists())
        self.assertTrue(result['timed_out'])
        self.assertLess(result['returncode'], 0)
        self.assertEqual(command_tree.exit_receipt(self.directory)[0], result['returncode'])
