"""Shared paths and fixtures for the application tests.

Parity tests compare the application with frozen experiment files (tracked).
Some also need the MMLongBench-Doc PDFs or notebook outputs, which are
git-ignored; those tests are skipped, with a reason, when the files are absent.
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_DOCUMENTS = REPO_ROOT / "data" / "documents"
MMLB_DOCUMENTS = REPO_ROOT / "data" / "external" / "mmlongbench_doc" / "documents"
MMLB_QUESTIONS = REPO_ROOT / "data" / "external" / "mmlongbench_doc" / "data" / "train-00000-of-00001.parquet"
FROZEN_E0_IMAGE_SETTINGS = REPO_ROOT / "experiments" / "frozen" / "mmlongbench_doc" / "image_run_20261119T232847Z_65ccf1ef" / "settings.json"
FROZEN_E0_TEXT_RUN = REPO_ROOT / "experiments" / "frozen" / "mmlongbench_doc" / "text_run_20261119T220858Z_a351a532"
FROZEN_E1_LOG = REPO_ROOT / "experiments" / "frozen" / "e1" / "run_20261121T131525011829Z_29c92c8a_full" / "execution_log.jsonl"
E1_SPEC = REPO_ROOT / "experiments" / "specs" / "e1_image_resolution_v1.json"
E3_SPEC = REPO_ROOT / "experiments" / "specs" / "e3_text_image_fusion_v1.json"
PAGES_PARQUET = REPO_ROOT / "data" / "processed" / "mmlongbench_doc" / "pages.parquet"


def read_json(path):
    return json.loads(Path(path).read_text())


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


@pytest.fixture
def mmlb_pdf():
    """Path of a downloaded MMLongBench-Doc PDF, or skip (run notebook 00 to download)."""

    def locate(doc_id):
        path = MMLB_DOCUMENTS / doc_id
        if not path.is_file():
            pytest.skip(f"{doc_id} not downloaded (git-ignored; notebook 00 downloads it)")
        return path

    return locate
