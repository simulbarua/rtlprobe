"""Bounded Python file writer only; no HDL targets, case replay or model calls."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from rtlprobe import evidence_limits


class CaptureFileLimitTests(unittest.TestCase):
    @unittest.skipUnless(evidence_limits.supported(),'RLIMIT_FSIZE unavailable')
    def test_inflight_file_limit_with_synthetic_python_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'bounded.bin'
            result=subprocess.run([sys.executable,str(Path(evidence_limits.__file__)), '--bytes','4096','--',
                sys.executable,'-c','import pathlib,sys;pathlib.Path(sys.argv[1]).write_bytes(b"x"*8192)',str(output)],
                cwd=tmp,capture_output=True,text=True,timeout=10)
            self.assertNotEqual(result.returncode,0)
            self.assertTrue(output.exists())
            self.assertLessEqual(output.stat().st_size,4096)

    def test_unsupported_or_invalid_policy_never_executes(self):
        with patch.object(evidence_limits,'supported',return_value=False),patch.object(evidence_limits.os,'execvp') as execute:
            with self.assertRaises(RuntimeError):evidence_limits.exec_limited(['target'],4096)
            execute.assert_not_called()
        for size in (0,True,1023,64*1024*1024+1):
            with patch.object(evidence_limits,'supported',return_value=True),patch.object(evidence_limits.os,'execvp') as execute:
                with self.assertRaises(ValueError):evidence_limits.exec_limited(['target'],size)
                execute.assert_not_called()


if __name__=='__main__':unittest.main()
