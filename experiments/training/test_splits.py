"""
Split-reader checks on synthetic group records (no package needed).

    python -m unittest test_splits -v
"""

import json
import tempfile
import unittest
from pathlib import Path

import splits


def group(lineage, eligible=True, site=None, template="t"):
    return {"split": "final_candidate" if eligible else "development_only", "final_test_eligible": eligible,
            "lineage_group": lineage, "design_group": lineage, "related_site_group": site or lineage,
            "operator_template_group": f"{lineage}-{template}"}


GROUPS = {"a1": group("A"), "a2": group("A"), "b1": group("B"), "c1": group("C"), "d1": group("D", eligible=False)}


class SplitTests(unittest.TestCase):
    def manifest(self, **parts):
        f = Path(tempfile.mkdtemp()) / "split.json"
        f.write_text(json.dumps({"split_id": "test", **parts}), encoding="utf-8")
        return f

    def refuses(self, msg, **parts):
        with self.assertRaisesRegex(splits.SplitError, msg):
            splits.held_out(self.manifest(**parts), list(GROUPS), GROUPS)

    def test_accepts_train_validation_test(self):
        s = splits.held_out(self.manifest(train=["a1", "a2"], validation=["b1"], test=["c1"]), list(GROUPS), GROUPS)
        self.assertEqual((s["train"], s["validation"], s["test"]), (["a1", "a2"], ["b1"], ["c1"]))
        self.assertEqual(s["result_label"], "held_out_test")

    def test_validation_is_optional(self):
        s = splits.held_out(self.manifest(train=["a1"], test=["c1"]), list(GROUPS), GROUPS)
        self.assertEqual(s["validation"], [])

    def test_missing_manifest(self):
        with self.assertRaisesRegex(splits.SplitError, "needs a frozen split manifest"):
            splits.held_out(None, list(GROUPS), GROUPS)

    def test_sample_in_two_partitions(self):
        self.refuses("both train and validation", train=["a1", "b1"], validation=["b1"], test=["c1"])

    def test_shared_lineage_train_test(self):
        self.refuses("train and test share lineage_group", train=["a1"], test=["a2"])

    def test_shared_lineage_validation_test(self):
        self.refuses("validation and test share", train=["b1"], validation=["a1"], test=["a2"])

    def test_development_only_in_test(self):
        self.refuses("development_only", train=["a1"], test=["d1"])

    def test_unknown_sample(self):
        self.refuses("unknown samples", train=["a1"], test=["zz"])

    def test_dev_smoke_label(self):
        dev = {"x": group("X", eligible=False)}
        s = splits.dev_smoke(["x"], dev)
        self.assertEqual(s["result_label"], "in_sample_smoke_test")
        self.assertEqual(s["validation"], [])
        with self.assertRaises(splits.SplitError):
            splits.dev_smoke(["a1"], GROUPS)


if __name__ == "__main__":
    unittest.main()
