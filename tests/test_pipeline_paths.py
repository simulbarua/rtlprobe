"""Exercise output routing with actual native HDL tools, when installed."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ("iverilog", "vvp", "verilator", "yosys")


@unittest.skipUnless(all(shutil.which(tool) for tool in TOOLS), "Native HDL tools unavailable")
class NativePipelinePathTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="rtlprobe native smoke ")
        self.addCleanup(self.workspace.cleanup)
        self.repo = Path(self.workspace.name).resolve()
        inputs = self.repo / "vendor/fixture"
        inputs.mkdir(parents=True)
        (inputs / "smoke.v").write_text(
            "module smoke(input wire a, output wire y);\n"
            "  assign y = a;\n"
            "endmodule\n"
        )
        (inputs / "testbench.v").write_text(
            "module testbench;\n"
            "  reg a; wire y; smoke dut(a, y);\n"
            "  initial begin\n"
            '    $dumpfile("testbench.vcd"); $dumpvars(0, testbench);\n'
            '    a = 0; #1; if (y !== 0) $fatal(1, "unexpected low output");\n'
            '    a = 1; #1; if (y !== 1) $fatal(1, "unexpected high output");\n'
            '    $display("NATIVE_SMOKE_OK"); $finish;\n'
            "  end\n"
            "endmodule\n"
        )
        # Run actual vvp with a bounded subprocess on hosts without GNU timeout.
        bin_dir = self.repo / "bin"
        bin_dir.mkdir()
        timeout = bin_dir / "timeout"
        timeout.write_text(
            f"#!{sys.executable}\n"
            "import subprocess, sys\n"
            "try:\n"
            "    result = subprocess.run(sys.argv[2:], timeout=float(sys.argv[1]))\n"
            "    sys.exit(result.returncode)\n"
            "except subprocess.TimeoutExpired:\n"
            "    sys.exit(124)\n"
        )
        timeout.chmod(0o755)
        self.env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"])

    def run_pipeline(self, output=None):
        command = [
            "bash", str(ROOT / "tooling/run_pipeline.sh"),
            "vendor/fixture/smoke.v", "vendor/fixture/testbench.v", "smoke",
        ]
        if output is not None:
            command.append(output)
        result = subprocess.run(
            command, cwd=self.repo, env=self.env, capture_output=True, text=True, timeout=60
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def assert_artifacts(self, output):
        status = dict(
            line.split(": ", 1) for line in (output / "status.txt").read_text().splitlines()
        )
        for stage in ("iverilog_compile", "simulation", "waveform", "verilator_lint", "yosys_synth", "ast_dump"):
            self.assertEqual(status[stage], "PASS", (output / "logs").as_posix())
        self.assertIn("NATIVE_SMOKE_OK", (output / "logs/sim.log").read_text())
        self.assertIn("smoke", json.loads((output / "synth/netlist.json").read_text())["modules"])
        self.assertTrue((output / "src/smoke.v").is_file())
        self.assertGreater((output / "waveform/wave.vcd").stat().st_size, 0)
        self.assertFalse((self.repo / "testbench.vcd").exists())

    def test_default_output_is_under_repository_outputs(self):
        self.run_pipeline()
        runs = list((self.repo / "outputs").glob("smoke__tb-testbench__*"))
        self.assertEqual(len(runs), 1)
        self.assert_artifacts(runs[0])
        self.assertFalse((self.repo / "results").exists())

    def test_explicit_output_is_respected(self):
        self.run_pipeline("outputs/custom-run")
        self.assert_artifacts(self.repo / "outputs/custom-run")
        self.assertEqual([p.name for p in (self.repo / "outputs").iterdir()], ["custom-run"])


if __name__ == "__main__":
    unittest.main()
