"""Test the host/container command boundary without requiring Docker."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="rtlprobe launcher ")
        self.addCleanup(self.workspace.cleanup)
        base = Path(self.workspace.name).resolve()
        self.repo = base / "repository with spaces"
        (self.repo / "tooling").mkdir(parents=True)
        self.launcher = self.repo / "tooling/pipeline.sh"
        shutil.copy2(ROOT / "tooling/pipeline.sh", self.launcher)
        self.outside = base / "outside"
        self.outside.mkdir()
        self.bin = base / "bin"
        self.bin.mkdir()
        docker = self.bin / "docker"
        docker.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "print(json.dumps(sys.argv[1:]))\n"
            "sys.exit(int(os.environ.get('LAUNCHER_TEST_EXIT_CODE', '0')))\n"
        )
        docker.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"])

    def launch(self, arguments, cwd=None, env=None):
        return subprocess.run(
            [str(self.launcher), *arguments],
            cwd=cwd or self.repo,
            env=env or self.env,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_same_repository_mounted_from_root_tooling_and_outside(self):
        arguments = ["vendor/design/rtl", "vendor/design/tb.v", "design"]
        for cwd in (self.repo, self.repo / "tooling", self.outside):
            with self.subTest(cwd=cwd):
                result = self.launch(arguments, cwd=cwd)
                self.assertEqual(result.returncode, 0, result.stderr)
                call = json.loads(result.stdout)
                self.assertEqual(call[0], "run")
                self.assertIn("--rm", call)
                self.assertEqual(call[call.index("--volume") + 1], f"{self.repo}:/workspace")
                self.assertEqual(call[call.index("--workdir") + 1], "/workspace")
                image = call.index("rtlprobe-tools")
                self.assertEqual(call[image + 1:], ["./tooling/run_pipeline.sh", *arguments])

    def test_quoted_inputs_and_output_remain_separate_arguments(self):
        arguments = [
            "vendor/design with spaces/rtl",
            "vendor/design with spaces/tb.v",
            "design",
            "outputs/run with spaces;$(touch SHOULD_NOT_EXIST)",
        ]
        result = self.launch(arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[-4:], arguments)
        self.assertFalse((self.repo / "SHOULD_NOT_EXIST").exists())

    def test_invalid_argument_counts_never_invoke_docker(self):
        for arguments in ([], ["rtl", "tb"], ["rtl", "tb", "top", "out", "extra"]):
            with self.subTest(arguments=arguments):
                result = self.launch(arguments)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("Usage:", result.stderr)

    def test_docker_failure_is_returned_to_caller(self):
        result = self.launch(
            ["vendor/design/rtl", "vendor/design/tb.v", "design"],
            env=dict(self.env, LAUNCHER_TEST_EXIT_CODE="17"),
        )
        self.assertEqual(result.returncode, 17)


if __name__ == "__main__":
    unittest.main()
