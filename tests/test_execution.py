"""Main execution is independent of model workflows and runtime-specific metadata."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rtlprobe import execution
from rtlprobe.evidence import manifest

class ExecutionTests(unittest.TestCase):
    def test_sealed_bundle_checked_inside_execution_transaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp);(bundle/'mutations.jsonl').write_text('{"fixture": true}\n');manifest(bundle)
            accepted=[]
            def run(path,validate_plan):
                items=[json.loads(s) for s in Path(path).read_text().splitlines()]
                validate_plan(items,{}, {}, {});accepted.append(items);return {'permitted':True}
            with patch.object(execution.batch,'run',side_effect=run):
                self.assertEqual(execution.run(bundle),{'permitted':True})
                (bundle/'mutations.jsonl').write_text('{"changed": true}\n')
                with self.assertRaises(ValueError):execution.run(bundle)
                self.assertEqual(len(accepted),1)
    def test_bundle_hash_pins_the_client_validated_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp);(bundle/'mutations.jsonl').write_text('{}\n');manifest(bundle)
            def run(path,validate_plan):
                validate_plan([{}],{}, {}, {})
            with patch.object(execution.batch,'run',side_effect=run):
                with self.assertRaisesRegex(ValueError,'caller-validated'):
                    execution.run(bundle,'0'*64)
    def test_plain_proposals_without_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'proposals.jsonl';file.write_text('{}\n')
            with patch.object(execution.batch,'run') as run:
                execution.run(file);self.assertEqual(run.call_args.args[0],file.resolve())
    def test_main_cli_has_no_agent_actions(self):
        import subprocess,sys
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,str(root/'scripts/rtlprobe.py'),'--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        for action in ['prepare','provenance','--prompt']:
            self.assertNotIn(action,result.stdout)

if __name__=='__main__':unittest.main()
