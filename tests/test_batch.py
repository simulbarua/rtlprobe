import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from rtlprobe import batch
from rtlprobe.evidence import (ROOT, Runner, filehash, load, manifest, save, workspace_lock, write_once)
from rtlprobe.lifecycle import (mutation_key, publish, reserve_attempt, verify_index)
from rtlprobe.mutation import apply, locate_constant
from test_pilot import PASS, classify

OP = {"id": "literal_lsb_flip32", "version": "1.0", "status": "approved"}


class ConstantTests(unittest.TestCase):
    def test_hex_and_decimal_localparam(self):
        for value, expected in [("32'h6a09e667", "32'h6a09e666"), ("63", "62")]:
            data = f"module m;\nlocalparam P = {value};\nendmodule\n".encode()
            target = locate_constant(data, 2, "P", f"localparam P = {value};")
            self.assertEqual(apply(data, target, OP), data.replace(value.encode(), expected.encode()))

    def test_case_assignment(self):
        data = b"module m;\nreg [31 : 0] x;\nreg r;\nalways @* case(r)\n0: x = 32'h428a2f98;\n1: x = 32'h71374491;\nendcase\nendmodule\n"
        target = locate_constant(data, 5, "x", "0: x = 32'h428a2f98;")
        self.assertEqual(apply(data, target, OP), data.replace(b"428a2f98", b"428a2f99"))

    def test_reject_signed_unknown_width_expression(self):
        for value in ("32'sh6a09e667", "16'h1234", "32'h1234567x", "63 + 1", "2147483648"):
            data = f"module m;\nlocalparam P = {value};\nendmodule\n".encode()
            with self.subTest(value=value), self.assertRaises(ValueError):
                locate_constant(data, 2, "P", f"localparam P = {value};")

    def test_stale_and_unapproved_constant(self):
        data = b"module m;\nlocalparam P = 63;\nendmodule\n"
        target = locate_constant(data, 2, "P", "localparam P = 63;")
        for source, changed_target, operator in ((data+b"\n", target, OP),
                (data, dict(target, end_byte=0), OP), (data, target, dict(OP, status="proposed"))):
            with self.assertRaises(ValueError):
                apply(source, changed_target, operator)

    def test_stray_error_cannot_pass(self):
        self.assertEqual(classify(PASS+"Error! Expected: 0x"+"a"*64)["outcome"], "infrastructure_error")


class RecoveryTests(unittest.TestCase):
    def test_immutable_write_and_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"record.json"
            write_once(path, {"state": "accepted_core"})
            with self.assertRaises(ValueError): write_once(path, {"state": "pending"})
            self.assertEqual(load(path)["state"], "accepted_core")
            with workspace_lock(tmp):
                with self.assertRaises(RuntimeError):
                    with workspace_lock(tmp): pass
            with workspace_lock(tmp): pass

    def test_incomplete_attempt_preserved_and_retry_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def new():
                out = root/f"attempt{len(list(root.glob('attempt*')))}"
                out.mkdir();return out
            state, first, recovered = reserve_attempt(root, "key", "fp", new)
            (first/"partial.log").write_text("do not overwrite")
            state, second, recovered = reserve_attempt(root, "key", "fp", new)
            self.assertNotEqual(first, second)
            self.assertEqual((first/"partial.log").read_text(), "do not overwrite")
            self.assertEqual(load(first/"INTERRUPTED.json")["status"], "interrupted")
            with self.assertRaises(RuntimeError): reserve_attempt(root, "key", "fp", new)

    def test_sealed_case_recovered_without_new_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); out=root/"attempt";out.mkdir()
            reserve_attempt(root,"key","fp",lambda:out)
            save(out/"case.json",{"mutation_key":"key"});manifest(out)
            _, recovered, sealed=reserve_attempt(root,"key","fp",lambda:self.fail("must not execute again"))
            self.assertEqual(recovered,out);self.assertTrue(sealed)

    def test_changed_inputs_refuse_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/"attempt";out.mkdir()
            reserve_attempt(root,"key","fp",lambda:out)
            with self.assertRaises(ValueError): reserve_attempt(root,"key","changed",lambda:out)

    def test_live_tool_blocks_recovery(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/"attempt";out.mkdir()
            reserve_attempt(root,"key","fp",lambda:out)
            save(out/"commands/run/process.json",{"pid":os.getpid()})
            with self.assertRaises(RuntimeError): reserve_attempt(root,"key","fp",lambda:out)

    def test_interrupt_kills_process_group_and_records_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc=Mock();proc.pid=12345;proc.wait.side_effect=[KeyboardInterrupt,-9];proc.poll.return_value=None
            runner=Runner(tmp,{"campaign_seconds":10,"cpu_seconds":10,"disk_bytes":100000})
            with patch("rtlprobe.evidence.subprocess.Popen",return_value=proc), patch("rtlprobe.evidence.os.killpg") as kill:
                with self.assertRaises(KeyboardInterrupt): runner.run("run",["test"],tmp,1)
                kill.assert_called_once()
            self.assertTrue(load(Path(tmp)/"commands/run/run.json")["interrupted"])

    def test_content_key_ignores_limits_but_changes_with_mutant(self):
        config={"rtl":["a"],"testbench":"tb","repository_url":"repo","revision":"rev",
                "top":"top","test_top":"tb","compile_flags":[],"defines":[],"parameters":{},"seed":None}
        original=mutation_key(config,{"a":"original","tb":"checker"},"a","mutant")
        self.assertEqual(original,mutation_key(dict(config,limits={"max_candidates":10}),{"a":"original","tb":"checker"},"a","mutant"))
        self.assertNotEqual(original,mutation_key(config,{"a":"original","tb":"checker"},"a","other"))

    def test_accepted_publication_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/"case";out.mkdir()
            record={"case_id":"case1","mutation_key":"key","state":"validated_pending_review",
                    "ground_truth":{},"cost":{}}
            save(out/"case.json",record);(out/"mutation.patch").write_text("patch");manifest(out)
            summary=publish(root,out,record)
            review={"decision":"approve","manifest_sha256":summary['case_manifest_sha256']}
            save(root/"review.json",review)
            event={"to_state":"accepted_core","human_review_sha256":filehash(root/"review.json"),
                   "case_manifest_sha256":summary['case_manifest_sha256']}
            save(root/"acceptance.json",event)
            summary.update(state="accepted_core",acceptance_record="acceptance.json",acceptance_sha256=filehash(root/"acceptance.json"),
                           human_review_record="review.json",human_review_sha256=filehash(root/"review.json"))
            save(root/"data/manifests/case1.json",summary)
            before=(root/"data/manifests/case1.json").read_bytes()
            self.assertEqual(publish(root,out,record)["state"],"accepted_core")
            other=root/"other";other.mkdir();save(other/"case.json",dict(record,extra=True));manifest(other)
            with self.assertRaises(ValueError): publish(root,other,record)
            self.assertEqual((root/"data/manifests/case1.json").read_bytes(),before)


class OutcomeTests(unittest.TestCase):
    """Exercise early-stop dispositions through the real case controller, with mocked tools."""
    def run_disposition(self, outcome):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/"case";out.mkdir()
            config=load(ROOT/"targets/sha256/config.json")
            proposal={"path":config['rtl'][0],"target":{"line":1,"column_1based":1,"before":"+","after":"-","statement":"a + b;"},
                      "family":"datapath_arithmetic","lineage_id":"site","activation":"test","prediction":{"first_checkpoint":"tc1"}}
            design={"structure":{"status":"pass"},"evidence":"qualification"}
            def snapshot(c,d):
                d.mkdir(parents=True);p=d/config['rtl'][0];p.parent.mkdir(parents=True);p.write_bytes(b"a + b;")
            def restore(name,cmd,cwd,timeout):
                (cwd/config['rtl'][0]).write_bytes(b"a + b;")
            good={"outcome":"pass","signature":None,"source_hashes":{},"executable_sha256":"bin"}
            first=dict(good,outcome=outcome)
            with patch.object(batch.pilot,"snapshot",side_effect=snapshot), patch.object(batch.pilot,"compile_design",return_value=out/"binary"), \
                 patch.object(batch.pilot,"simulate",side_effect=[good,first,good]) as sim, \
                 patch.object(batch.Runner,"require",side_effect=restore), patch.object(batch.pilot,"schema"), \
                 patch.object(batch.pilot,"structure") as synthesis:
                record=batch.execute(proposal,config,{"sha256":"fp"},design,"key",b"a + b;",b"a - b;",out,60)
                self.assertEqual(sim.call_count,3) # Original, one mutant, restored; no pointless replays.
                synthesis.assert_not_called()
                return record

    def test_survivor_is_unexposed_not_equivalent(self):
        record=self.run_disposition("pass")
        self.assertEqual(record['state'],"unexposed");self.assertEqual(record['automated_validation'],"fail")

    def test_timeout_is_not_a_functional_bug(self):
        record=self.run_disposition("timeout_unclassified")
        self.assertEqual(record['state'],"infrastructure_error")


if __name__ == "__main__": unittest.main()
