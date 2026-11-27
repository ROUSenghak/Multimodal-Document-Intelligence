"""Frozen S-v2 owner-label packages for E9, E10 and the final evaluation (labelled 2026-11-27)."""

import csv
import hashlib
import json

import pytest

from conftest import REPO_ROOT

FIELDS = ["document", "evidence_pages", "question", "answer_format", "reference", "reply"]


@pytest.mark.parametrize("package, source, tally", [
    ("e9_scoring_v2", "e9", {"correct": 7, "wrong": 6, "unsure": 0}),
    ("e10_scoring_v2", "e10", {"correct": 9, "wrong": 8, "unsure": 0}),
    ("final_scoring_v2", "final", {"correct": 53, "wrong": 32, "unsure": 0}),
])
def test_owner_labels_match_their_sealed_blind_queue(package, source, tally):
    folder = REPO_ROOT / "experiments" / "frozen" / package
    entries = [line.split(maxsplit=1) for line in (folder / "SHA256SUMS").read_text().splitlines()]
    assert sorted(name for _, name in entries) == ["PROVENANCE.json", "README.md", "adjudication_key.csv", "adjudication_labels.csv"]
    for expected, name in entries:
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == expected, name

    labels = list(csv.DictReader((folder / "adjudication_labels.csv").open(encoding="utf-8")))
    assert {label: sum(row["label"] == label for row in labels) for label in tally} == tally
    assert json.loads((folder / "PROVENANCE.json").read_text())["labels"] == tally

    # Every label covers exactly one blind item and is bound to its exact text.
    adjudication = REPO_ROOT / "experiments" / "frozen" / source / "adjudication"
    queue = {row["item_id"]: row for row in csv.DictReader((adjudication / "blind_queue_unlabelled.csv").open(encoding="utf-8"))}
    assert set(queue) == {row["item_id"] for row in labels} and len(labels) == len(queue)
    for row in labels:
        payload = {field: str(queue[row["item_id"]][field]) for field in FIELDS}
        assert hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest() == row["identity_sha256"]

    # The unblinding key is the sealed key, copied without edits.
    assert (folder / "adjudication_key.csv").read_bytes() == (adjudication / "sealed_key.csv").read_bytes()


def test_labels_shared_across_packages_never_disagree():
    seen = {}
    for package in ("scoring_v2", "e8_scoring_v2", "e9_scoring_v2", "e10_scoring_v2", "final_scoring_v2"):
        for row in csv.DictReader((REPO_ROOT / "experiments" / "frozen" / package / "adjudication_labels.csv").open(encoding="utf-8")):
            assert seen.setdefault(row["identity_sha256"], row["label"]) == row["label"], (package, row["item_id"])
