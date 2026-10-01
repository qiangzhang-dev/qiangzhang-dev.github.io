"""Read-only, post-hoc audit of decision-relevant discount conditions.

Standard library only. No model loading, inference, training, or network calls.
Run from this directory: python split_audit.py > /tmp/sft-split-audit.json
The input fingerprints pin this audit to the published 2026-10-01 source snapshot.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re

SOURCE_COMMIT = "8ff7032e8deceffad2d368ea844160cdfe315608"
SOURCE_BASE = ("https://github.com/qiangzhang-dev/qiangzhang-dev.github.io/blob/"
               + SOURCE_COMMIT + "/experiments/sft-explanation/")
SOURCE_SHA256 = {
    "data/train.json": "9b41f719734416c4469695237738d506e9b22de7356837fa7feed26b4400e258",
    "data/test.json": "7c0e67b4b302ea382118d78f0205fee75e1b6215d3c2181bee9bbecba740bac2",
    "followup/results/explained-seed17-original.json": "761cb535a8806ec44a92c8c112503f03025f8113f48fe2d9ef27fa3363fc9dbd",
    "followup/results/explained-seed29-original.json": "f74fcecc92b9a1a1957eb00f24840f062b4d67fa359d858a708064981080bc60",
}


def condition(row):
    """Shipping is explicitly excluded by the task; equal labels are not a key."""
    task, goods, shipping, threshold = row["id"].split("-")
    if task != "discount" or row["task"] != "discount":
        raise ValueError("Only discount rows have this decision-condition key")
    int(shipping)
    return int(goods), int(threshold)


def audit(root):
    sources = {}
    provenance = {}
    for relative, expected_sha in SOURCE_SHA256.items():
        content = (root / relative).read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != expected_sha:
            raise ValueError(f"Published source fingerprint mismatch: {relative}")
        sources[relative] = json.loads(content)
        provenance[relative] = {"sha256": digest, "url": SOURCE_BASE + relative}

    train = sources["data/train.json"]
    test = sources["data/test.json"]
    train_ids = {row["id"] for row in train}
    test_ids = {row["id"] for row in test}
    if train_ids & test_ids or ({row["question"] for row in train} & {row["question"] for row in test}):
        raise ValueError("Full train/test IDs or prompts overlap")
    groups = {}
    for name, rows in [("train", train), ("test", test)]:
        grouped = defaultdict(list)
        for row in rows:
            if row["task"] == "discount":
                goods, threshold = condition(row)
                if row["answer"] != (20 if goods >= threshold else 0):
                    raise ValueError(f"Incorrect reference label: {row['id']}")
                grouped[(goods, threshold)].append(row)
        groups[name] = grouped

    rows = [row for row in test if row["task"] == "discount"]
    item_evidence = []
    for row in rows:
        item_evidence.append({
            "test_id": row["id"], "subtotal_threshold": list(condition(row)),
            "expected": row["answer"],
            "matching_training_ids": [item["id"] for item in groups["train"].get(condition(row), [])],
        })

    results = {}
    for seed in [17, 29]:
        tag = f"explained-seed{seed}"
        relative = f"followup/results/{tag}-original.json"
        raw = {row["id"]: row for row in sources[relative]["records"]}
        strata = {"seen_condition": {"n": 0, "correct": 0}, "unseen_condition": {"n": 0, "correct": 0}}
        for row, evidence in zip(rows, item_evidence):
            output = raw[row["id"]]
            if output["question"] != row["question"] or output["expected"] != row["answer"] or output["hit_limit"]:
                raise ValueError(f"Unexpected raw-record contract: {tag}/{row['id']}")
            # These saved discount outputs all end with a plain integer Answer field.
            # Reject anything else rather than generalizing the extraction rule.
            match = re.search(r"\bAnswer:\s*(-?\d+)\.\s*$", output["output"])
            if match is None:
                raise ValueError(f"No terminal integer Answer: {tag}/{row['id']}")
            value = int(match[1])
            correct = value == row["answer"]
            if output["parsed"] != value or output["correct"] != correct:
                raise ValueError(f"Saved score disagrees with raw answer: {tag}/{row['id']}")
            evidence.setdefault("original_final_values", {})[tag] = value
            stratum = "seen_condition" if condition(row) in groups["train"] else "unseen_condition"
            strata[stratum]["n"] += 1
            strata[stratum]["correct"] += int(correct)
        results[tag] = {"raw_source": relative, "strata": strata}

    train_keys, test_keys = set(groups["train"]), set(groups["test"])
    return {
        "audit_date": "2026-10-01", "source_commit": SOURCE_COMMIT,
        "method": "Post-hoc grouping by (item subtotal, discount threshold). Shipping is explicitly irrelevant to the reference decision. Recount saved original-question outputs only; no new inference or training.",
        "split": {
            "train_rows": sum(map(len, groups["train"].values())), "train_distinct_conditions": len(train_keys),
            "test_rows": len(rows), "test_distinct_conditions": len(test_keys),
            "test_rows_with_training_condition": sum(bool(row["matching_training_ids"]) for row in item_evidence),
            "test_distinct_conditions_seen_in_training": len(train_keys & test_keys),
            "test_rows_with_unseen_condition": sum(not row["matching_training_ids"] for row in item_evidence),
            "test_distinct_conditions_unseen_in_training": len(test_keys - train_keys),
        },
        "original_question_results": results,
        "item_evidence": item_evidence,
        "caveats": [
            "Full question strings and full parameter tuples are disjoint; decision-relevant conditions need not be.",
            "Four unseen-condition test rows cover only three distinct conditions. This is a tiny, post-hoc descriptive subset, not an independent benchmark.",
            "Both seeds use the same test items. The counts do not establish memorization or explain the SFT-target difference.",
            "Original data, protocols, raw outputs, and headline scores are unchanged."
        ],
        "provenance": provenance,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    print(json.dumps(audit(args.root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
