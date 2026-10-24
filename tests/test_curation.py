"""Curation transitions over synthetic temporary bundles; no simulations or benches."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from rtlprobe import curation
from rtlprobe.evidence import CODE_ROOT, filehash, identity, load, manifest, save, treehashes, workspace_lock
from rtlprobe.lifecycle import existing_cases, publish, verify_index


class CurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        with workspace_lock(self.root):
            pass
        self.audit = patch("rtlprobe.pilot.audit").start()
        self.addCleanup(patch.stopall)

    def case(self, cid, ordinal, design="design", operator="operator", **overrides):
        record = {"case_id": cid, "mutation_key": cid, "state": "validated_pending_review",
                  "design_id": design, "proposal": {"operator": {"id": operator}, "path": "dut.v",
                                                     "prediction": {"first_checkpoint": "cp1"}},
                  "automated_validation": "pass", "prediction_agreement": "confirmed",
                  "mutants": [{"signature": [{"id": "cp1"}]}],
                  "checks": {"restored_source_identity": True, "restored_pass": True},
                  "ground_truth": {}, "cost": {}}
        record.update(overrides)
        out = self.root/"outputs"/design/"cases"/f"{cid}-20261024T0000{ordinal:02d}000000Z"
        out.mkdir(parents=True)
        save(out/"case.json", record)
        save(out/"fingerprint.json", {"inputs": {"config": {}, "files": {}}})
        (out/"mutation.patch").write_text("synthetic fixture; no source or testbench")
        manifest(out)
        publish(self.root, out, record)
        return out

    def summary(self, cid):
        return load(self.root/"data/manifests"/(cid+".json"))

    def receipt(self, cid):
        return load(self.root/self.summary(cid)["acceptance_record"])

    def approve(self, cid, decision="approve", **kwargs):
        return curation.accept(self.root, cid, "Test reviewer", decision, "Reviewed saved evidence", **kwargs)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(CODE_ROOT/"scripts/rtlprobe.py"),
                               "--data-root", str(self.root), *args], capture_output=True,
                              text=True, timeout=30, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))

    def test_timestamp_rank_first_n_and_separate_pairs(self):
        # Insertion and lexical case-id orders both disagree with timestamp order.
        for ordinal in (6, 2, 5, 3, 1, 4):
            self.case(f"case-{7-ordinal}", ordinal)
        self.case("other-design", 7, design="other")
        self.case("other-operator", 8, operator="other")
        sealed = {p: filehash(p) for p in self.root.glob("outputs/**/case.json")}
        results = curation.promote_auto(self.root)
        self.assertEqual([r["case_id"] for r in results[:6]], [f"case-{n}" for n in range(6, 0, -1)])
        self.assertEqual([r["rank"] for r in results[:6]], list(range(1, 7)))
        self.assertTrue(all(r["reasons"] == ["first_n_human_review"] for r in results[:5]))
        self.assertEqual(results[5]["action"], "PROMOTE")
        self.assertEqual([r["rank"] for r in results[6:]], [1, 1])
        self.audit.assert_called_once()
        self.assertEqual(self.summary("case-1")["accepted_auto"], 1)
        self.assertEqual(self.summary("case-1")["accepted_core"], 0)
        self.assertEqual(self.summary("case-1")["validated_pending_review"], 0)
        verify_index(self.root, self.summary("case-1"))
        self.assertEqual(existing_cases(self.root)["case-1"]["state"], "accepted_auto")
        self.assertEqual(sealed, {p: filehash(p) for p in sealed})
        self.assertEqual(load(self.root/"data/labels/case-1.json")["status"], "accepted_auto")
        self.assertEqual(load(self.root/"data/reviews/case-1.json")["status"], "pending")

    def test_rank_includes_human_and_rejected_but_not_terminal_failures(self):
        self.case("approved", 1)
        self.approve("approved")
        self.case("rejected", 2)
        self.approve("rejected", "reject")
        self.case("unexposed", 3, state="unexposed")
        self.case("pending", 4)
        result = curation.promote_auto(self.root, first_n=2)
        self.assertEqual([(r["case_id"], r["rank"], r["action"]) for r in result], [("pending", 3, "PROMOTE")])
        self.case("later", 5)
        self.assertEqual(curation.promote_auto(self.root, first_n=3)[0]["rank"], 4)

    def test_each_sealed_hold_independently_and_annotation_ignored(self):
        variants = [({"automated_validation": "fail"}, "automated_validation_not_pass"),
                    ({"prediction_agreement": "unexpected_failure_needs_review"}, "prediction_agreement_not_confirmed"),
                    ({"mutants": [{"signature": [{"id": "cp2"}]}]}, "unexpected_first_checkpoint"),
                    ({"checks": {"restored_pass": False}}, "check_failed:restored_pass")]
        for i, (override, expected) in enumerate(variants):
            self.case(f"held-{i}", i, **override)
        self.case("good", 10)
        save(self.root/"data/annotations/good.json", {"hold_reasons": ["must_be_ignored"], "automated_validation": "fail"})
        results = curation.promote_auto(self.root, first_n=0)
        self.assertEqual([r["reasons"] for r in results[:4]], [[v[1]] for v in variants])
        self.assertEqual(results[4]["action"], "PROMOTE")
        self.assertEqual(self.audit.call_count, 1)
        self.assertTrue(all(self.summary(f"held-{i}")["state"] == "validated_pending_review" for i in range(4)))

    def test_audit_failure_blocks_promotion_without_writing(self):
        from jsonschema import ValidationError
        self.case("bad-audit", 1)
        before = treehashes(self.root)
        for failure in (ValueError("saved log mismatch"), ValidationError("invalid sealed case schema")):
            self.audit.side_effect = failure
            result = curation.promote_auto(self.root, first_n=0)
            self.assertEqual(result[0]["reasons"], ["audit_failed:"+str(failure)])
            self.assertEqual(treehashes(self.root), before)

    def test_dry_run_reads_audit_but_changes_no_content(self):
        self.case("candidate", 1)
        before = treehashes(self.root)
        result = curation.promote_auto(self.root, first_n=0, dry_run=True)
        self.assertEqual(result[0]["action"], "PROMOTE")
        self.audit.assert_called_once()
        self.assertEqual(treehashes(self.root), before)
        result = self.cli("promote-auto", "--first-n", "1", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'HOLD candidate pair=(design, operator) rank=1 reasons=["first_n_human_review"]\n')
        self.assertEqual(treehashes(self.root), before)

    def test_auto_receipt_tampering_with_rebound_summary_is_rejected(self):
        self.case("auto", 1)
        curation.promote_auto(self.root, first_n=0)
        summary, receipt = self.summary("auto"), self.receipt("auto")
        variants = [{"case_manifest_sha256": "0"*64}, {"to_state": "accepted_core"},
                    {"reviewer": "Not automatic"}, {"validation_sha256": "0"*64},
                    {"validation_record": "other/case.json"}, {"human_review_record": "review.json"},
                    {"policy": dict(receipt["policy"], hold_reasons=["unexpected_first_checkpoint"])},
                    {"policy": dict(receipt["policy"], rank=0)},
                    {"policy": dict(receipt["policy"], first_n=1)}]
        path = self.root/summary["acceptance_record"]
        for changed in variants:
            with self.subTest(changed=changed):
                save(path, dict(receipt, **changed))
                with self.assertRaises(ValueError):
                    verify_index(self.root, dict(summary, acceptance_sha256=filehash(path)))
        save(path, receipt)
        with self.assertRaises(ValueError):
            verify_index(self.root, dict(summary, acceptance_sha256="0"*64))

    def test_auto_receipt_recomputes_sealed_holds(self):
        out = self.case("auto", 1)
        curation.promote_auto(self.root, first_n=0)
        record = load(out/"case.json")
        record["checks"]["restored_pass"] = False
        save(out/"case.json", record)
        manifest(out)
        summary, receipt = self.summary("auto"), self.receipt("auto")
        receipt.update(case_manifest_sha256=filehash(out/"manifest.json"), validation_sha256=filehash(out/"case.json"))
        save(self.root/summary["acceptance_record"], receipt)
        summary.update(case_manifest_sha256=filehash(out/"manifest.json"), acceptance_sha256=filehash(self.root/summary["acceptance_record"]))
        with self.assertRaisesRegex(ValueError, "unresolved holds"):
            verify_index(self.root, summary)

    def test_human_approval_uses_unchanged_core_verifier_and_previous_hashes(self):
        self.case("human", 1)
        paths = [self.root/"data"/folder/"human.json" for folder in ("manifests", "labels", "reviews")]
        previous = dict(zip(("index_sha256", "label_sha256", "review_sha256"), map(filehash, paths)))
        summary = self.approve("human")
        self.assertEqual(summary["state"], "accepted_core")
        self.assertEqual(summary["accepted_core"], 1)
        self.assertEqual(summary["accepted_auto"], 0)
        self.assertEqual(self.receipt("human")["previous_record_hashes"], previous)
        verify_index(self.root, summary)
        self.assertEqual(existing_cases(self.root)["human"]["state"], "accepted_core")
        before = treehashes(self.root)
        with self.assertRaises(ValueError):
            self.approve("human")
        self.assertEqual(treehashes(self.root), before)

    def test_rejection_and_receipt_bindings(self):
        self.case("rejected", 1)
        summary = self.approve("rejected", "reject")
        self.assertEqual(summary["state"], "rejected")
        self.assertEqual((summary["accepted_core"], summary["accepted_auto"]), (0, 0))
        self.assertEqual(load(self.root/"data/labels/rejected.json")["status"], "rejected")
        self.assertFalse((self.root/"data/reviews/policy").exists())
        verify_index(self.root, summary)
        self.assertEqual(existing_cases(self.root)["rejected"]["state"], "rejected")
        receipt = self.receipt("rejected")
        for changed in ({"validation_sha256": "0"*64}, {"case_manifest_sha256": "0"*64},
                        {"human_review_sha256": "0"*64}, {"to_state": "accepted_core"}):
            save(self.root/summary["acceptance_record"], dict(receipt, **changed))
            with self.assertRaises(ValueError):
                verify_index(self.root, dict(summary, acceptance_sha256=filehash(self.root/summary["acceptance_record"])))

    def test_sample_rejection_preserves_auto_history_and_holds_future_pair(self):
        for ordinal in range(1, 4):
            self.case(f"auto-{ordinal}", ordinal)
        curation.promote_auto(self.root, first_n=0)
        _, sample = curation.sample_auto(self.root)
        cid = sample["sample"][0]
        old = self.receipt(cid)
        old_hash = self.summary(cid)["acceptance_sha256"]
        self.approve(cid, "reject")
        self.assertEqual(self.receipt(cid)["previous_record_hashes"]["acceptance_sha256"], old_hash)
        archive = self.root/"data/reviews/history"/cid/(old_hash+".acceptance.json")
        self.assertEqual(load(archive), old)
        self.assertEqual(filehash(archive), old_hash)
        policy_path = self.root/"data/reviews/policy/design__operator.json"
        policy = load(policy_path)
        self.assertTrue(policy["full_review"])
        self.assertEqual(policy["rejected_case_id"], cid)
        self.case("future", 4)
        result = curation.promote_auto(self.root, first_n=0)
        self.assertEqual(result[0]["reasons"], ["pair_under_full_review"])
        # A later policy changes eligibility, never the meaning of an earlier receipt.
        counts = curation.audit_data(self.root)["counts"]
        self.assertEqual((counts["accepted_auto"], counts["rejected"]), (2, 1))
        self.assertEqual(curation.audit_data(self.root)["pairs"][0]["held_with_reasons"][0]["case_id"], "future")
        before = treehashes(self.root)
        self.assertEqual(curation.promote_auto(self.root, first_n=0, dry_run=True)[0]["action"], "HOLD")
        self.assertEqual(treehashes(self.root), before)

    def test_sampled_approval_upgrades_auto_to_core(self):
        self.case("auto", 1)
        curation.promote_auto(self.root, first_n=0)
        curation.sample_auto(self.root, fraction=0.5)
        summary = self.approve("auto")
        self.assertEqual(summary["state"], "accepted_core")
        self.assertEqual(self.receipt("auto")["policy"]["fraction"], 0.5)
        self.assertFalse((self.root/"data/reviews/policy").exists())
        verify_index(self.root, summary)

    def test_sample_determinism_fraction_and_pair_floor(self):
        for i in range(20):
            self.case(f"many-{i:02d}", i)
        self.case("rare", 21, design="rare")
        curation.promote_auto(self.root, first_n=0)
        before = {p: filehash(p) for p in self.root.glob("data/manifests/*.json")}
        path, sample = curation.sample_auto(self.root)
        _, again = curation.sample_auto(self.root)
        self.assertEqual(sample["sample"], again["sample"])
        self.assertEqual(sample["seed"], identity(sample["population"]))
        self.assertEqual(len(sample["sample"]), 3)
        self.assertIn("rare", sample["sample"])
        self.assertEqual(sample["fraction"], curation.DEFAULT_FRACTION)
        self.assertEqual(set(sample["first_n_by_case"].values()), {0})
        self.assertTrue(path.name.endswith(".json"))
        _, floor = curation.sample_auto(self.root, fraction=0.001)
        self.assertEqual(len(floor["sample"]), 2)
        self.assertIn("rare", floor["sample"])
        self.assertEqual(before, {p: filehash(p) for p in before})
        self.assertEqual(curation.sample_auto(self.root, fraction=1)[1]["sample"], sample["population"])

    def test_empty_sample_and_invalid_arguments_do_not_create_cases(self):
        _, sample = curation.sample_auto(self.root)
        self.assertEqual(sample["sample"], [])
        for fraction in (0, -0.1, 1.1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                curation.sample_auto(self.root, fraction)
        for first_n in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                curation.promote_auto(self.root, first_n)
        for cid in ("../escape", "missing"):
            with self.assertRaises(ValueError):
                self.approve(cid)

    def test_cli_accept_document_sample_and_split_audit(self):
        self.case("human", 1)
        self.case("auto", 2)
        self.case("pending", 3, design="other")
        self.case("rejected", 4)
        document = self.root/"review.txt"
        document.write_text("A synthetic review document.\n")
        result = self.cli("accept", "human", "--reviewer", "Reviewer", "--decision", "approve",
                          "--evidence", "Inspected outcomes", "--document", str(document))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(load(self.root/"data/reviews/human.json")["document"]["sha256"], filehash(document))
        self.approve("rejected", "reject")
        curation.promote_auto(self.root, first_n=1)
        result = self.cli("sample-auto", "--fraction", "0.25")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["sample"], ["auto"])
        result = self.cli("audit-data")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["counts"], {"accepted_auto": 1, "accepted_core": 1, "rejected": 1, "validated_pending_review": 1})
        self.assertEqual(report["pairs"][0]["accepted_core"], 1)
        self.assertEqual(report["pairs"][0]["accepted_auto"], 1)
        self.assertNotIn("accepted", report["counts"])
        self.assertEqual(report["fresh_simulations"], 0)

    def test_all_actions_obey_workspace_lock(self):
        self.case("pending", 1)
        before = treehashes(self.root)
        with workspace_lock(self.root):
            for action in (lambda: curation.promote_auto(self.root), lambda: curation.sample_auto(self.root),
                           lambda: self.approve("pending"), lambda: curation.audit_data(self.root)):
                with self.assertRaises(RuntimeError):
                    action()
        self.assertEqual(treehashes(self.root), before)

    def test_schema_checks_every_receipt_before_writing(self):
        self.case("candidate", 1)
        before = treehashes(self.root)
        with patch.object(curation, "validate_receipt", side_effect=ValueError("schema failure")):
            with self.assertRaisesRegex(ValueError, "schema failure"):
                curation.promote_auto(self.root, first_n=0)
            with self.assertRaisesRegex(ValueError, "schema failure"):
                self.approve("candidate")
        self.assertEqual(treehashes(self.root), before)

    def test_receipt_example_matches_published_schema(self):
        from jsonschema import Draft202012Validator
        for ordinal in range(1, 6):
            self.case(f"first-{ordinal}", ordinal)
        self.case("example-auto", 6)
        with patch.object(curation, "_now", return_value="20261024T120000000000Z"):
            curation.promote_auto(self.root)
        event = self.receipt("example-auto")
        schema = load(CODE_ROOT/"rtlprobe/schemas/curation_v2.json")
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(event)
        curation.validate_receipt(event)
        self.example_receipt = event


if __name__ == "__main__":
    unittest.main()
