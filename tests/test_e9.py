"""Regression guards for the frozen E9 packages (notebook 08). No API call, no test-pool data."""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "experiments" / "frozen"


def _sha256sums_ok(folder: Path) -> dict[str, bool]:
    entries = [line.split(maxsplit=1) for line in (folder / "SHA256SUMS").read_text().splitlines() if line.strip()]
    return {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest for digest, name in entries}


@pytest.mark.parametrize("package", ["e9_stage0", "e9"])
def test_frozen_e9_packages_equal_their_checksums(package):
    checks = _sha256sums_ok(FROZEN / package)
    assert checks and all(checks.values()), [name for name, ok in checks.items() if not ok]


def test_e9_stage0_selected_trigger_and_gate():
    summary = json.loads((FROZEN / "e9_stage0" / "tables" / "stage0_summary.json").read_text())
    assert summary["stage0_passed"] is True
    assert summary["selected_trigger"] == "U3_flatness_18"
    assert summary["selected_threshold"] == -0.153079
    assert summary["population"] == {"P0": 101, "P_deploy": 118, "documents": 14}
    gate = summary["gate"]
    assert [name for name, row in gate.items() if row["passes"]] == ["U3_flatness_18"]
    assert round(gate["U3_flatness_18"]["auroc"], 3) == 0.783
    assert summary["headroom"] == {"complete_at_8_not_4": 8, "incomplete_at_4": 39, "no_evidence_in_top_8": 11, "recoverable_ranks_5_8": 15}


def test_e9_stage2_verdict_counts_and_spend():
    summary = json.loads((FROZEN / "e9" / "tables" / "evaluation_summary.json").read_text())
    assert summary["decision"]["VERDICT (S-v1, frozen rules)"] == "no_meaningful_gain"
    assert {arm: row["S-v1 correct / 102"] for arm, row in summary["arms"].items()} == {
        "B1s": 44, "F8a": 46, "F8b": 46, "A1a": 47, "A1b": 46}
    assert summary["decision"]["per replicate"]["A1a"]["broken"] == 0
    assert summary["decision"]["per replicate"]["A1b"]["broken"] == 0
    assert summary["new_blind_items"] == 13
    provenance = json.loads((FROZEN / "e9" / "PROVENANCE.json").read_text())
    assert provenance["cumulative_cost_usd"] == pytest.approx(0.15164664, abs=1e-8)
    assert provenance["cumulative_cost_usd"] <= provenance["ceiling_usd"] == 0.50
    assert provenance["served_identity"]["models"] == ["gpt-6-luna"]


def test_e9_b1s_requests_equal_frozen_e8_l_b1():
    def records(path):
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    e8 = {r["qid"]: r["fingerprint"] for r in records(next((FROZEN / "e8").glob("run_*_full")) / "execution_log.jsonl") if r["arm"] == "L-B1"}
    e9 = {r["qid"]: r["fingerprint"] for r in records(next((FROZEN / "e9").glob("run_*_full")) / "execution_log.jsonl") if r["arm"] == "B1s"}
    assert len(e9) == 118 and e9 == e8
