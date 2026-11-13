"""Per-command refusal and durable stop outcomes using mocked child processes."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from rtlprobe import pilot
from rtlprobe.evidence import Runner,load,environment


class CommandGuardTests(unittest.TestCase):
    def test_runner_scoped_hooks_bind_launch_and_see_durable_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);guard=Mock(return_value=True)
            guard.before_command.return_value=True;guard.after_command.return_value=True
            def after(record):
                self.assertEqual(load(root/'commands/one/run.json'),record)
                return True
            guard.after_command.side_effect=after
            runner=Runner(root,{'campaign_seconds':30,'cpu_seconds':30,'disk_bytes':100000},execution_guard=guard)
            with patch('subprocess.Popen',return_value=Mock(pid=12345,wait=Mock(return_value=0))):
                record=runner.run('one',['synthetic'],root,1)
            guard.before_command.assert_called_once_with('one',['synthetic'],str(root),1)
            guard.after_command.assert_called_once_with(record)

    def test_source_query_hooks_bind_both_fixed_git_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);vendor=root/'vendor';vendor.mkdir();(vendor/'rtl.v').write_text('module m;endmodule')
            guard=Mock(return_value=True);guard.before_command.return_value=True;guard.after_command.return_value=True
            cfg={'vendor':'vendor','revision':'a'*40,'rtl':['rtl.v'],'testbench':'tb.v','collateral':[]}
            (vendor/'tb.v').write_text('module tb;endmodule')
            with patch.object(pilot,'ROOT',root),patch('subprocess.check_output',side_effect=['a'*40,'']):
                self.assertEqual(set(pilot.inputs(cfg,execution_guard=guard)),{'rtl.v','tb.v'})
            self.assertEqual([call.args[0] for call in guard.before_command.call_args_list],['source_revision','source_status'])
            for call in guard.before_command.call_args_list:
                self.assertEqual(call.args[1][:3],['git','-C',str(vendor)]);self.assertEqual(call.args[3],15)
            self.assertEqual(guard.after_command.call_count,2)

    def test_version_probes_stop_after_revocation_without_next_query(self):
        allowed=[True]
        def query(*args,**kwargs):
            self.assertEqual(kwargs['timeout'],15)
            allowed[0]=False
            return Mock(stdout='version',stderr='',returncode=0)
        with patch('subprocess.run',side_effect=query) as run,patch('shutil.which',return_value='/synthetic/tool'):
            with self.assertRaisesRegex(ValueError,'guard'):environment(execution_guard=lambda:allowed[0])
            self.assertEqual(run.call_count,1)

    def test_source_git_probes_require_guard_before_and_after_query(self):
        allowed=[False]
        with patch('subprocess.check_output') as query:
            with self.assertRaisesRegex(ValueError,'guard'):
                pilot.inputs({'vendor':'vendor/toy'},execution_guard=lambda:allowed[0])
            query.assert_not_called()
            allowed[0]=True
            def done(*args,**kwargs):
                self.assertEqual(kwargs['timeout'],15);allowed[0]=False
                return 'revision'
            query.side_effect=done
            with self.assertRaisesRegex(ValueError,'guard'):
                pilot.inputs({'vendor':'vendor/toy'},execution_guard=lambda:allowed[0])
            self.assertEqual(query.call_count,1)

    def test_nonliteral_guard_refuses_before_output_or_child(self):
        with tempfile.TemporaryDirectory() as tmp,patch('subprocess.Popen') as child:
            path=Path(tmp)/'work'
            with self.assertRaisesRegex(ValueError,'guard'):
                Runner(path,{},execution_guard=lambda:1)
            self.assertFalse(path.exists());child.assert_not_called()

    def test_revocation_after_child_preserves_record_and_prevents_next_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);allowed=[True]
            runner=Runner(root,{'campaign_seconds':30,'cpu_seconds':30,'disk_bytes':100000},execution_guard=lambda:allowed[0])
            child=Mock(pid=12345)
            def done(**kwargs):allowed[0]=False;return 0
            child.wait.side_effect=done
            with patch('subprocess.Popen',return_value=child) as launch:
                with self.assertRaisesRegex(ValueError,'guard'):runner.run('one',['synthetic'],root,1)
                self.assertEqual(load(root/'commands/one/run.json')['returncode'],0)
                with self.assertRaisesRegex(ValueError,'guard'):runner.run('two',['synthetic'],root,1)
                self.assertEqual(launch.call_count,1);self.assertFalse((root/'commands/two').exists())
