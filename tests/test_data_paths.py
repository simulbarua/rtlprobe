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
            result=subprocess.run([sys.executable,str(ROOT/'scripts/rtlprobe.py'),'--data-root',str(data),'paths'],cwd=tmp,capture_output=True,text=True,timeout=20,env=dict(os.environ,RTLPROBE_DATA_ROOT='/ignored'))
            self.assertEqual(result.returncode,0,result.stderr);info=json.loads(result.stdout)
            self.assertEqual(info['rtlprobe_root'],str(ROOT));self.assertEqual(info['data_root'],str(data))
            self.assertIsNone(info['config']);self.assertFalse(data.exists())
    def test_relative_or_nested_data_root_rejected(self):
        for data in ['relative',str(ROOT/'outputs'),str(ROOT),str(ROOT.parent)]:
            result=subprocess.run([sys.executable,str(ROOT/'scripts/rtlprobe.py'),'--data-root',data,'paths'],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,2);self.assertNotIn('Traceback',result.stderr)
    def test_cli_help_lists_runner_actions(self):
        result = subprocess.run(
            [sys.executable, str(ROOT/'scripts/rtlprobe.py'), '--help'],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('{paths,fetch,check,qualify,run,audit,audit-data,accept,promote-auto,sample-auto}',
                      result.stdout)

if __name__=='__main__':unittest.main()
