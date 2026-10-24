"""Explicit external data selection through the stable main-repository script."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class DataPathTests(unittest.TestCase):
    def test_external_root_from_unrelated_cwd(self):
        with tempfile.TemporaryDirectory(prefix='RTLProbe independent data ') as tmp:
            data=Path(tmp).resolve()/'data with spaces'
            result=subprocess.run([sys.executable,str(ROOT/'scripts/rtlprobe.py'),'--data-root',str(data),'paths'],cwd=tmp,capture_output=True,text=True,timeout=20,env=dict(os.environ,RTLPROBE_DATA_ROOT='/ignored',RTLPROBE_PROMPT='/ignored'))
            self.assertEqual(result.returncode,0,result.stderr);info=json.loads(result.stdout)
            self.assertEqual(info['rtlprobe_root'],str(ROOT));self.assertEqual(info['data_root'],str(data));self.assertNotIn('prompt',info)
            self.assertIsNone(info['config']);self.assertFalse(data.exists())
    def test_relative_or_nested_data_root_rejected(self):
        for data in ['relative',str(ROOT/'outputs'),str(ROOT),str(ROOT.parent)]:
            result=subprocess.run([sys.executable,str(ROOT/'scripts/rtlprobe.py'),'--data-root',data,'paths'],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,2);self.assertNotIn('Traceback',result.stderr)
    def test_no_embedded_agent_or_prompt_package(self):
        self.assertFalse((ROOT/'rtlprobe/agents').exists());self.assertFalse((ROOT/'rtlprobe/prompts').exists())
        self.assertFalse((ROOT/'rtlprobe/planning.py').exists())
        self.assertFalse((ROOT/'rtlprobe/schemas/planner_provenance.json').exists())
        self.assertTrue((ROOT/'rtlprobe/execution.py').exists())

if __name__=='__main__':unittest.main()
