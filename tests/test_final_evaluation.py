"""Regression guards for the frozen final held-out evaluation (notebook 09). No API call; no question or reply text read."""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "experiments" / "frozen"


def _sha256sums_ok(folder: Path) -> dict[str, bool]:
    entries = [line.split(maxsplit=1) for line in (folder / "SHA256SUMS").read_text().splitlines() if line.strip()]
    return {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest for digest, name in entries}


@pytest.mark.parametrize("package", ["final_index", "final_retrieval", "final"])
def test_final_packages_equal_their_checksums(package):
    checks = _sha256sums_ok(FROZEN / package)
    assert checks and all(checks.values()), [name for name, ok in checks.items() if not ok]


def test_final_index_was_built_without_reading_questions():
    summary = json.loads((FROZEN / "final_index" / "index_summary.json").read_text())
    assert summary["questions_read"] is False and summary["parity_gate"] is True
    assert summary["documents_verified"] == 110 and summary["pages"] == 5554
    assert [row["doc_id"] for row in summary["excluded"]] == ["mi_phone.pdf"]


def test_final_claims_and_verdicts():
    s = json.loads((FROZEN / "final" / "tables" / "evaluation_summary.json").read_text())
    assert (s["questions"], s["documents"], s["triggered"]) == (872, 110, 335)
    assert (s["C1"]["overall"]["correct"], s["C1"]["overall"]["n"]) == (288, 674)
    assert (s["C1"]["core scope"]["correct"], s["C1"]["core scope"]["n"]) == (77, 207)
    assert s["C2"]["verdict"] == "visual_retrieval_confirmed" and (s["C2"]["fixed"], s["C2"]["broken"]) == (103, 23)
    assert round(s["C2"]["delta"], 4) == 0.1187
    assert s["C3"]["verdict"] == "a1_gain_supported" and (s["C3"]["fixed"], s["C3"]["broken"]) == (19, 5)
    assert {arm: row["S-v1 correct"] for arm, row in s["arms"].items()} == {"B1": 288, "T1": 208, "A1": 302, "F8": 84}
    assert s["D2_s1_exceptions"] == {"none": 1605, "reply not numeric": 2}
    assert s["S_v2_ranges"]["pending items"] == 85 and s["S_v2_ranges"]["B1 - T1"][0] > 0 and s["S_v2_ranges"]["A1 - B1"][0] > 0


def test_final_run_identity_and_cost():
    provenance = json.loads((FROZEN / "final" / "PROVENANCE.json").read_text())
    assert provenance["runs"]["full"]["calls"] == provenance["runs"]["full"]["attempts"] == 2079
    assert provenance["served_identity"]["models"] == ["gpt-6-luna"]
    assert provenance["cumulative_cost_usd"] == pytest.approx(0.99344918, abs=1e-8)
    assert provenance["cumulative_cost_usd"] <= provenance["ceiling_usd"] == 2.50
    audit = json.loads((FROZEN / "final" / "AUDIT.json").read_text())
    failed = sorted(check["name"].split()[0] for check in audit["checks"] if not check["passed"])
    assert failed == ["1.15", "5.03"]  # both low severity and documented in experiments/frozen/final/README.md and the ledger
