"""Read-only checks for the dated SFT split audit and its frozen inputs."""

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "experiments/sft-explanation"
SPEC = importlib.util.spec_from_file_location("split_audit", ROOT / "split_audit.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class SftSplitAuditTests(unittest.TestCase):
    def test_committed_result_reproduces_without_network_or_writes(self):
        before = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                  for name in AUDIT.SOURCE_SHA256}
        with patch.object(socket, "socket", side_effect=AssertionError("network prohibited")):
            with patch.object(Path, "write_text", side_effect=AssertionError("writes prohibited")):
                with patch.object(Path, "write_bytes", side_effect=AssertionError("writes prohibited")):
                    result = AUDIT.audit(ROOT)
        self.assertEqual(result, json.loads((ROOT / "split_audit.json").read_text()))
        self.assertEqual(before, {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                  for name in AUDIT.SOURCE_SHA256})

    def test_decision_key_ignores_only_shipping(self):
        row = lambda name: {"id": name, "task": "discount"}
        self.assertEqual(AUDIT.condition(row("discount-170-15-180")),
                         AUDIT.condition(row("discount-170-35-180")))
        self.assertNotEqual(AUDIT.condition(row("discount-170-15-180")),
                            AUDIT.condition(row("discount-170-15-200")))
        with self.assertRaises(ValueError):
            AUDIT.condition({"id": "inventory-7-6-2", "task": "inventory"})

    def test_changed_source_fails_with_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative in AUDIT.SOURCE_SHA256:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, destination)
            (root / "data/train.json").write_text("[]")
            with self.assertRaisesRegex(ValueError, "fingerprint mismatch: data/train.json"):
                AUDIT.audit(root)

    def test_conditions_and_descriptive_counts(self):
        result = AUDIT.audit(ROOT)
        self.assertEqual(result["split"], {
            "train_rows": 32, "train_distinct_conditions": 20,
            "test_rows": 12, "test_distinct_conditions": 9,
            "test_rows_with_training_condition": 8,
            "test_distinct_conditions_seen_in_training": 6,
            "test_rows_with_unseen_condition": 4,
            "test_distinct_conditions_unseen_in_training": 3,
        })
        for seed, correct in [(17, 3), (29, 4)]:
            self.assertEqual(result["original_question_results"][f"explained-seed{seed}"]["strata"]["unseen_condition"],
                             {"n": 4, "correct": correct})

    def test_cli_output_is_byte_identical(self):
        run = subprocess.run([sys.executable, str(ROOT / "split_audit.py")],
                             check=True, capture_output=True)
        self.assertEqual(run.stdout, (ROOT / "split_audit.json").read_bytes())
        self.assertEqual(run.stderr, b"")

    def test_addendum_keeps_original_publication_date(self):
        report = (ROOT / "results/index.html").read_text()
        self.assertIn('id="split-audit-2026-10-01"', report)
        self.assertIn("2026-10-01 补充：按决策条件检查数据划分", report)
        self.assertIn("2026-09-29 · Qiang (Nate) Zhang", report)


if __name__ == "__main__":
    unittest.main()
