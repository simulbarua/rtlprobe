import copy
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys

from baseline import distances, evaluate, extract, rank
from run_sha256 import parse_anchor, trace_evidence


class LocalizationTests(unittest.TestCase):
    def test_cross_module_register_and_control_cone(self):
        sources = {"design.v": """module child(input clk, input en, input d, output reg q);
always @(posedge clk) if (en) q <= d;
endmodule
module top(input clk, input enable, input data, output result);
wire mid;
child u(.clk(clk), .en(enable), .d(data), .q(mid));
assign result = mid;
endmodule
"""}
        graph = extract(sources, "top", "tb.dut")
        cone = distances(graph["dependencies"], ["tb.dut.result"])
        self.assertIn("tb.dut.u.q", cone)
        self.assertIn("tb.dut.data", cone)
        self.assertIn("tb.dut.enable", cone)
        self.assertIn("tb.dut.clk", cone)
        assignment = next(c for c in graph["candidates"] if c["module"] == "child")
        self.assertTrue(assignment["sequential"])

    def test_named_block_signal_mapping(self):
        graph = extract({"x.v": """module top(input a, output reg y);
always @* begin : arithmetic
reg temp;
temp = a;
y = temp;
end
endmodule"""}, "top", "tb.dut")
        self.assertEqual(graph["dependencies"]["tb.dut.y"], ["tb.dut.arithmetic.temp"])
        self.assertEqual(graph["dependencies"]["tb.dut.arithmetic.temp"], ["tb.dut.a"])

    def test_multiple_assignments_on_one_line_are_one_location(self):
        graph = extract({"x.v": """module top(input a, output reg y);
always @* begin y=0; y=a; end
endmodule"""}, "top", "tb.dut")
        self.assertEqual(len(graph["candidates"]), 1)
        self.assertEqual(graph["candidates"][0]["lhs"], ["tb.dut.y"])
        self.assertEqual(graph["dependencies"]["tb.dut.y"], ["tb.dut.a"])

    def test_reject_parameter_override_and_positional_ports(self):
        for connection in ("child #(.N(2)) u(.a(a), .y(y));", "child u(a,y);"):
            source = "module child(input a, output y); parameter N=1; assign y=a; endmodule\n"
            source += "module top(input a, output y); " + connection + " endmodule"
            with self.assertRaises(ValueError):
                extract({"x.v": source}, "top", "tb.dut")

    def payload(self):
        graph = extract({"x.v": "module top(input a, output y); assign y=a; endmodule"},
                        "top", "tb.dut")
        return {"schema_version": "test", "mode": "rtl_logs_structure", "sources": {},
                "failure_log": "y mismatch", "candidates": graph["candidates"],
                "structure": graph, "anchor": "tb.dut.y"}

    def test_labels_rejected_and_evaluation_does_not_change_predictions(self):
        payload = self.payload()
        with self.assertRaises(ValueError):
            rank(dict(payload, ground_truth={"path": "x.v", "line": 1}))
        result = rank(payload)
        before = copy.deepcopy(result)
        self.assertEqual(evaluate(result, {"path": "x.v", "line": 1})["reciprocal_rank"], 1)
        missing = evaluate(result, {"path": "absent.v", "line": 9})
        self.assertEqual(missing["reciprocal_rank"], 0)
        self.assertFalse(missing["candidate_inclusion"])
        self.assertEqual(result, before)

    def test_trace_timescale_history_clip_and_value_agreement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.vcd"
            path.write_text("""$timescale 1ps $end
$scope module tb_sha256_core $end
$scope module dut $end
$var wire 4 ! digest [3:0] $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
b0000 !
#1000
b0011 !
#2000
b1111 !
""")
            anchor = {"time_units": 1, "tb_time_unit_exponent": -9, "actual": "3",
                      "signal": "tb_sha256_core.dut.digest"}
            graph = {"dependencies": {"tb_sha256_core.dut.digest": []}}
            trace = trace_evidence(path, anchor, graph)
            self.assertEqual(trace["window_end_tick"], 1000)
            self.assertEqual(trace["signals"][anchor["signal"]]["events"], [(0, "0000"), (1000, "0011")])
            with self.assertRaises(ValueError):
                trace_evidence(path, dict(anchor, actual="4"), graph)

    def test_anchor_requires_actual_failure(self):
        log = "RTLPROBE_ANCHOR tc=1 time_units=12.000 expected=ff actual=ab"
        self.assertEqual(parse_anchor(log)["time_units"], 12)
        with self.assertRaises(ValueError):
            parse_anchor(log.replace("actual=ab", "actual=ff"))

    def test_ranker_runs_without_case_or_label_and_ignores_label_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            script = directory / "baseline.py"
            script.write_bytes(Path(__file__).with_name("baseline.py").read_bytes())
            (directory / "input.json").write_text(json.dumps(self.payload()))
            outputs = []
            for label in ("x.v:1", "unrelated.v:99"):
                (directory / "label.json").write_text(label)
                subprocess.run([sys.executable, script, directory / "input.json", directory / "out.json"],
                               cwd=directory, check=True, capture_output=True)
                outputs.append(json.loads((directory / "out.json").read_text())["ranking"])
            self.assertEqual(outputs[0], outputs[1])


if __name__ == "__main__":
    unittest.main()
