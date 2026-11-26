# VisualDoc AI: reproducibility guide

- **Date:** 2026-11-26.
- **Audience:** anyone who wants to re-derive the reported results, regenerate the intermediate files, or understand what cannot be reproduced.
- **Ground rules** (`AGENTS.md`): no paid call without the owner's explicit approval; never edit `experiments/frozen/`. The test pool has been used once, by the final evaluation: it may be reported, never used to tune a system (section 10).

---

## 1. Three levels of reproduction

| Level | What it re-establishes | Cost | Needs |
|---|---|---|---|
| **1. Re-derive frozen results** | every reported number, from the frozen requests and replies, with no API call | $0 | the repository, the environment, the outputs of the earlier notebooks |
| **2. Regenerate intermediate files** | page records, renders, BM25 rankings, ColQwen2 embeddings and rankings, request fingerprints | $0, but downloads and compute | network for the PDFs and the 4.4 GB ColQwen2 checkpoint; hours of CPU/GPU for embeddings |
| **3. Re-run live calls** | whether the models would answer the same way today | paid, and only with approval | API keys, a frozen spec, a budget; **not bit-reproducible** (section 7) |

Levels 1 and 2 are the default behaviour of the notebooks. Level 3 is never needed to check a result: the frozen replies define every result.

---

## 2. Environment

**Platform.** Developed and tested on macOS on Apple Silicon (a fanless M1 with 8 GB of RAM). The virtual environment uses Python 3.12.6 (`.venv/pyvenv.cfg`); `pyproject.toml` requires Python ≥ 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt          # = pip install -e ".[dev,notebooks]"
python -m ipykernel install --user --name visualdoc-venv --display-name "VisualDoc (.venv, Python 3.12)"
```

| Extra (`pyproject.toml`) | For | Contents |
|---|---|---|
| core | the application modules | `pymupdf` |
| `notebooks` | notebooks 00–03 and 05–08, offline replay and mocked API tests | numpy, pandas, pyarrow, matplotlib, jupyter, ipykernel, huggingface_hub, openai, python-dotenv, tiktoken, `transformers==5.23.0` (E2 token expectations only) |
| `visual` | notebook 04 (ColQwen2 encoding) and the application's live encoder | `torch==2.15.0`, `transformers==5.23.0`, pillow, psutil, safetensors |
| `llm` | the application's live mode | openai, python-dotenv, tiktoken |
| `dev` | tests | pytest |

Install the visual extra only if you will encode pages: `pip install -e ".[visual]"`. Re-ranking from cached embeddings needs only NumPy.

**Locked versions.** `requirements/lock-2026-11-26.txt` pins the full environment of 2026-11-26; `docs/ssp_cloud.md` uses it to rebuild the environment on a Linux datalab service.

**Kernel.** Every notebook's metadata names the kernel `visualdoc-venv`. Other kernels on the development machine looked plausible but pointed at another Python and broke imports; if an import fails in a notebook, check `sys.executable` before installing anything.

**OCR.** Tesseract runs through PyMuPDF with the English model in `resources/tessdata/`; no system Tesseract is needed.

**The macOS hidden `.pth` problem.** Symptom: `ModuleNotFoundError: No module named 'visualdoc'` although `pip show visualdoc-ai` works. Cause: the editable install's `.pth` file in `.venv/lib/python3.12/site-packages/` carries the macOS `hidden` flag, and Python skips hidden `.pth` files. Check with `ls -lO .venv/lib/python3.12/site-packages/*.pth`. Fix:

```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth
```

The flag comes back on its own in an iCloud-synced folder. Two workarounds do not depend on it: `pytest` already adds `src` to the path (`pythonpath = ["src"]` in `pyproject.toml`), and for scripts and the application, prefix the command with `PYTHONPATH=src`.

**Credentials.** Only live runs need keys. Copy `.env.example` to `.env` for the notebooks' paid modes (`OPENAI_API_KEY`; `OPENROUTER_API_KEY` for E2). `.env` is git-ignored; never commit or print it. The application never reads `.env`: export `OPENAI_API_KEY` in the shell for `--live`.

---

## 3. Data acquisition

| Data | Source and version | Fetched by | Stored |
|---|---|---|---|
| MMLongBench-Doc question table | `yubo2333/MMLongBench-Doc`, revision `2ff6aa9237fc777b6627dc57a486e9225ac5fb86` | tracked in git | `data/external/mmlongbench_doc/data/*.parquet` |
| 6 development PDFs (dev6) | same revision; seeded draw (seed 42) among documents ≤ 15 MB, listed without downloading first | notebook 00 (about 22 MB; OCR of 120 pages takes about a minute) | `data/external/mmlongbench_doc/documents/` (git-ignored) |
| 14 held-out development PDFs | same revision; two per benchmark type, seeded, ≤ 100 pages | notebook 04 | same folder |
| 111 test-pool PDFs | same revision; each kept only if its bytes equal the hash recorded at the revision (LFS SHA-256, or git blob SHA-1 for files stored in git); `mi_phone.pdf` fails and is excluded (deviation D1) | notebook 09, `index` mode | same folder; hashes in `experiments/frozen/final_index/pool_documents.csv` |
| ColQwen2 checkpoint | `vidore/colqwen2-v1.0-hf` at revision `ddc07d23`, weight SHA-256 recorded by E5 | notebook 04 (4.4 GB, once); for notebook 09, the Hugging Face cache outside the repository, with weight, preprocessor and tokenizer hashes equal to E5's (`docs/PROGRESS.md`) | `data/cache/hf/colqwen2-v1.0-hf@ddc07d2317c8/` (git-ignored) or the Hugging Face cache |
| Local sample PDFs | see `THIRD_PARTY_NOTICES.md` | tracked | `data/documents/` |

MMLongBench-Doc is licensed CC BY-NC 4.0, research use only. Network access is needed only for these downloads. Page numbering (benchmark page *p* = PyMuPDF index *p* − 1) is checked in notebooks 00 and 01, not assumed.

**The question table contains the test pool.** The pool has now been used by the final evaluation, but the rule against per-question analysis still holds. Do not print or browse pool rows of `data/external/mmlongbench_doc/data/*.parquet` or of `data/processed/mmlongbench_doc/questions.parquet` outside the notebooks' own code paths (section 10).

---

## 4. Notebook order and modes

Run the notebooks in order on the `visualdoc-venv` kernel, from a fresh kernel each time. Each reads only saved files from the earlier ones and stops with a clear message when an input is missing.

```bash
.venv/bin/jupyter nbconvert --execute --to notebook --inplace notebooks/00_document_processing.ipynb
# then 01, 02, … 09 in the same way
```

`--inplace` saves the outputs into the notebook, which is how the repository keeps its executed record.

| Notebook | Needs | Default mode | Verifies on every run |
|---|---|---|---|
| 00 | question table, network for 6 PDFs | — | page-number convention; the 124 page images the frozen image run sent, byte for byte |
| 01 | 00 | — | the frozen BM25 rankings (57/57); Recall@5 0.689, Hit@5 0.800 |
| 02 | 00, 01, `experiments/frozen/` | `VISUALDOC_QA_MODE=replay`; `VISUALDOC_E1_MODE` … `VISUALDOC_E4_MODE=offline` | page lists, prompts, parameters, token estimates and request fingerprints equal the frozen runs (E0–E4) |
| 03 | 00–02 | evaluates the frozen runs (`VISUALDOC_E1_RUN_DIR` … `VISUALDOC_E4_RUN_DIR` select another saved run) | A 7/40, B 7/40, C 9/40, D 11/38; E1–E4 references; per-question tables byte for byte |
| 04 | 00, 01, 14 PDFs, checkpoint or cached embeddings | no API at all | the held-out selection rule; arm A reproduces the frozen E0 and E4 runs; rankings, summary and per-question table regenerate exactly |
| 05 | 00, 04, frozen E4–E6 | `VISUALDOC_E6_MODE=offline` | `SHA256SUMS`; E6 tables byte for byte; A 25/102, V 38/102 |
| 06 | 00, 04, frozen E5–E7 | `VISUALDOC_E7_MODE=offline` | E7 tables byte for byte; V0 38, X4 31, X8 29 |
| 07 | 00, 04, frozen E5–E8, S-v2 labels | `VISUALDOC_QA_MODE=replay` | S-v1 scorer equals notebook 03's cell `f653d232`; 236/236 unique E8 requests rebuilt through the application; E8 evaluation |
| 08 | frozen E5, E8 and E9 packages | `VISUALDOC_E9_MODE=offline` | input checksums; spec equals its freeze commit; B1s requests equal frozen E8 L-B1; Stage 0 and Stage 2 evaluation |
| 09 | 00 (`questions.parquet`), the frozen spec and plan, `final_index`, `final_retrieval`, `final`; the final embeddings (`data/cache/final/`) and processed tables | `VISUALDOC_FINAL_MODE=offline` | spec equals its freeze commit `1c54a3e`; index frozen and committed; question embeddings complete; frozen rankings consistent; plan frozen; the evaluation reproduces its frozen copy (C1–C3, S-v2 ranges); paid gate closed |

The regression references each notebook asserts are listed in `AGENTS.md`; a change that breaks one must be explained, not silenced.

**Notebook 04's encoding step.** By default notebook 04 re-ranks from the cached embeddings in `data/cache/e5/`. If they are missing, it re-encodes the held-out pages: about 3 hours on the M1, minutes on a GPU, plus the 4.4 GB checkpoint download (`experiments/frozen/e5/README.md`). The two-pass encoding is checked to be bitwise identical to a single pass on every execution.

**Notebook 09's modes** (`VISUALDOC_FINAL_MODE`, notebook 09 cell `fe-title`):

| Mode | What it does | Reads questions? | Paid? | Machine |
|---|---|---|---|---|
| `offline` (default) | reports the state of every stage and evaluates the completed run | only once the index is frozen | no | any |
| `index` | downloads the pool PDFs and verifies their hashes (D1), extracts text (OCR below 30 words), renders 768-px pages, runs the E5 parity gate, then encodes every page with ColQwen2 (resumable, in 200-page chunks of the two-pass encoding) | **no** | no | **Apple M1 GPU only** |
| `queries` | after the index manifest is committed: loads the pool questions, encodes them, computes the rankings | yes | no | **Apple M1 GPU only** |
| `smoke` / `full` | the reader runs (smoke on development questions only) | yes | yes, with approval | any |

The encoding modes assert Apple MPS because the frozen specs require bit-for-bit equality with E5's embeddings, and another GPU type gives slightly different numbers. On any other machine, notebook 09 reads the frozen rankings in `experiments/frozen/final_retrieval/` and only checks that its recomputed scores agree with them within 1e-4 (`experiments/frozen/final_retrieval/README.md`; `docs/ssp_cloud.md`). All four of the final evaluation's stages have run; re-running `smoke` or `full` would be a second use of the pool and is not allowed.

**Figures** are regenerated, not checksummed: PNG and PDF bytes can differ across matplotlib versions, so they are checked by eye; the per-question tables are checked byte for byte (`experiments/frozen/e1/README.md`).

**Paid modes** (`smoke`, `pilot`, `full`) run only after the owner's explicit approval, in that order. Each invocation creates a new, exclusive run directory under `experiments/runs/<exp>/`, refuses to overwrite an earlier one, and checks every call against the spec's cumulative ceiling. `*_RESUME_DIR` variables continue an interrupted run; `*_RUN_DIR` variables evaluate a completed one.

---

## 5. Verifying frozen packages

Every frozen package carries a `SHA256SUMS` file covering every other file in it.

```bash
# one package
cd experiments/frozen/e6 && shasum -a 256 -c SHA256SUMS

# all packages, from the repository root
for d in experiments/frozen/*/; do
  if [ -f "$d/SHA256SUMS" ]; then
    (cd "$d" && shasum -a 256 -c --quiet SHA256SUMS >/dev/null && echo "OK   $d" || echo "FAIL $d")
  else
    echo "NONE $d"
  fi
done
```

On 2026-11-26 this loop reported `OK` for all 17 packages: `mmlongbench_doc`, `e1`–`e8`, `e8_smoke`, `scoring_v2`, `e8_scoring_v2`, `e9_stage0`, `e9`, `final_index`, `final_retrieval` and `final`.

**The final evaluation's embeddings are not in git** (about 1 GB under `data/cache/final/`). Every page embedding's SHA-256 is in `experiments/frozen/final_index/index_manifest.csv` and every query embedding's in `experiments/frozen/final_retrieval/query_manifest.csv`, so any copy, for example one restored from MinIO storage, can be verified against the frozen packages.

**Independent audit scripts** that ship with their package:
- `experiments/frozen/e7/audit_e7.py`: `python -I experiments/frozen/e7/audit_e7.py . AUDIT.json` from inside `experiments/frozen/e7/`. Its first check compares the package with the original git-ignored runs in `experiments/runs/e7/`, so it needs them.
- `experiments/frozen/e9_stage0/audit/audit_e9_stage0.py`: `.venv/bin/python experiments/frozen/e9_stage0/audit/audit_e9_stage0.py` from the repository root; its expected output is `audit/audit_output.txt`.
- `experiments/frozen/e9/audit/audit_e9_stage2.py`: `python audit_e9_stage2.py [REPO_ROOT] [OUT_DIR]` (read-only, no API call; `OUT_DIR` defaults to the script's folder, so pass a scratch folder to avoid writing inside the package); its recorded result is `experiments/frozen/e9/AUDIT.json` (47/47).
- `experiments/frozen/final/audit/audit_final.py`: `python audit_final.py [REPO_ROOT] [OUT_DIR] [--skip-maxsim]` (no API call, no question or reply text in its output). It also reads the git-ignored run directories and `data/processed/mmlongbench_doc/final/`, so it needs them. `OUT_DIR` defaults to the script's folder; pass a scratch folder. Its recorded result is `experiments/frozen/final/AUDIT.json`: 70 quantities reproduced to within 3.7e-11, 36 of 38 integrity checks passed, the two failures being documented low-severity findings (`docs/research_report.md` §7).

Other packages record their audit's checks and recomputed results in `AUDIT.json`; the scripts that produced them were run outside the repository.

---

## 6. Tests

```bash
pytest                                            # pythonpath = src is set in pyproject.toml
PYTHONPATH=src .venv/bin/python -m pytest -q      # the form docs/application.md uses
```

| Area | Examples |
|---|---|
| Pinned application | the five modules' SHA-256 equal the frozen E8 spec; parity with frozen requests and replies (`tests/test_b1.py`, `test_answering.py`, `test_retrieval.py`, `test_documents.py`, `test_citations.py`, `test_pipeline.py`) |
| Frozen packages | `SHA256SUMS` and label-identity hashes of the S-v2 packages, completeness of the E8 package (`tests/test_b1.py`); `SHA256SUMS` of `e9_stage0` and `e9`, the Stage 0 gate, the Stage 2 verdict, counts and spend, and B1s requests equal to frozen E8 L-B1 (`tests/test_e9.py`); checksums of the three final packages, an index built without reading questions, the frozen claims and verdicts, run identity and cost (`tests/test_final_evaluation.py`) |
| Application | visual index codec and keys, all 175 frozen E5 visual rankings reproduced from cached embeddings, offline answers, BM25 fallback, ceilings, pool guard, CLI, web server (`tests/test_visual_index.py`, `test_app.py`, `test_web.py`) |
| History | the unused `parsing.py` and the annotation schema (`tests/test_parsing.py`, `test_annotations.py`) |

Some tests depend on git-ignored caches (for example the E5 embeddings). When an input is missing, those tests are skipped as a whole rather than run on a smaller set (`docs/application.md` §6). The test count changes as the application evolves; read it from the pytest summary rather than from any document.

---

## 7. What cannot be reproduced without paying, and what cannot be reproduced at all

**Replies are not deterministic, even at temperature 0.** Identical requests give different replies across sessions:

| Where | Observed change between identical requests | Source |
|---|---|---|
| E0 text runs, 2026-11-19 | 3–6 of 57 predictions (no score change) | `experiments/README.md` |
| E1 512-px repeat | correctness of 1/37 | `experiments/frozen/e1/README.md` |
| E2 Qwen 768-px repeat; E3 IT repeat | correctness of 0/37 | `e2/README.md`, `e3/README.md` |
| E6 V vs E7 V0 (two sessions, same request) | 2 fixed, 2 broken | `experiments/frozen/e7/README.md` |
| E8 L-B1 vs L-B1r | 4 correctness flips (S-v1), 7 (S-v2) | `experiments/frozen/e8/README.md`; `docs/validated_baseline_b1.md` |
| E9 B1s vs frozen E8 L-B1, same day | 44 vs 46, 6 flips | `experiments/frozen/e9/README.md` |

The final evaluation ran one session with one run per arm, so it has no repeat measurement of its own; its README compares its effects with E8's 4–7 flips (`experiments/frozen/final/README.md`).

**Models that cannot be pinned or will disappear.**
- `gpt-6-luna` is an alias with no dated snapshot, and it returned no system fingerprint on any E8, E9 or final-evaluation call (`experiments/frozen/final/PROVENANCE.json`). A change in the served model or fingerprint is a new condition (`AGENTS.md`).
- `gpt-4o-mini-2024-07-18`, the reader of E0–E7, shuts down on 2027-01-14. After that, E0–E7 can be re-derived (level 1) but never re-run (level 3).
- Qwen3-VL-8B in E2 was served through OpenRouter; the hosted weight revision, image preprocessing and serving stack cannot be verified, and the slug can change.

**Provider-side caching.** OpenAI's prompt cache served part of some runs: in E1 it was confounded with time since the first request; in E9 most F8 calls reused a cached prompt prefix (replies were still generated afresh); in the final evaluation 157 calls carried cached prompt tokens (`experiments/frozen/final/AUDIT.json`, check 1.15). This lowers observed cost and may affect variability; it is recorded, not controlled.

**What a paid re-run would show** is therefore a new session of the same protocol, to be compared with the frozen one as a new condition, never a byte-identical reproduction. **The frozen replies, not the model names, define every result.**

---

## 8. iCloud `dataless` files

The repository lives in an iCloud-synced `Documents` folder on a nearly full disk. macOS evicts the content of some files to save space: an evicted ("dataless") file is still listed with its full size, but its bytes are downloaded again when it is read, which needs network access and free disk.

- **Check a file:** `ls -lO <path>` shows `compressed,dataless` for an evicted file.
- **What was evicted** (counted in `docs/PROGRESS.md`): 391 cached page images, 85 processed files, 12 source PDFs, 495 `.venv` files and 82 `.git` objects.
- **The ColQwen2 weights** (`data/cache/hf/colqwen2-v1.0-hf@ddc07d2317c8/model.safetensors`, 4.4 GB) are dataless. Materialising them would leave about 1.7 GB of disk free (`docs/PROGRESS.md`). The application checks the weights with `os.stat` only and refuses to enable the encoder rather than trigger the download (`docs/application.md` §3). E8, E9 and the offline application do not need them: they use E5's frozen rankings and cached embeddings. For the final evaluation's encoding, iCloud could not restore the file (the account's storage quota blocks sync), so the pinned revision was downloaded into the Hugging Face cache outside the repository instead; its hashes equal E5's (`docs/PROGRESS.md`).
- **Pool PDFs.** Three pool PDFs fetched during E5's selection had become placeholders; notebook 09 forces a fresh, hash-verified download for such files (`docs/PROGRESS.md`).
- **Consequences.** A notebook or test that reads an evicted file may stall or fail without network. Some PDFs of the development set are placeholders; E8's S-v2 adjudication used the cached 768-px renders, which are the images the reader received (`experiments/frozen/e8_scoring_v2/README.md`). The hidden-`.pth` problem (section 2) also comes from the synced folder.
- **Recommendation recorded in the design documents:** move the repository out of the iCloud-synced folder (`docs/baseline_b1_specification.md` §7). Before any run that needs the original PDFs, re-materialise them or re-download them with notebooks 00 and 04.

The frozen packages in `experiments/frozen/` had no dataless file on 2026-11-26, so section 5's checksum loop runs offline.

**Moving off the laptop.** The work is moving to an Onyxia datalab (the ENSAE-ENSAI Datalab, or SSP Cloud); `docs/ssp_cloud.md` is the step-by-step guide (code on GitHub, git-ignored data on MinIO, secrets in Vault, encoding kept on the M1). The lead reports that the upload of the final evaluation's embeddings to MinIO was verified, but that the datalab's storage filter blocked page images, PDFs and some tables. The PDFs can be downloaded again from Hugging Face and checked against the hashes in `experiments/frozen/final_index/pool_documents.csv`; page images are re-rendered and checked against the SHA-256 in `index_manifest.csv`. At the time of writing `docs/ssp_cloud.md` does not yet record the storage filter.

---

## 9. Resource needs

| Resource | Measured value | Source |
|---|---|---|
| Machine | fanless M1, 8 GB RAM | `docs/PROGRESS.md` |
| Free disk | 6.1 GB of 228 GB (97 % used) when last recorded | `docs/PROGRESS.md` |
| ColQwen2 indexing | **12.5 s per page** (9.8 s vision + 2.7 s language model), two passes required on 8 GB | `experiments/frozen/e5/README.md` |
| Query encoding / scoring | 0.16 s per query; about 4 ms to score a document | same |
| Embeddings | 193 KB per page (bf16) | same |
| Model | 4.4 GB of weights; about 3.3 GB peak GPU memory | `experiments/frozen/e5/README.md`, `e6/README.md` |
| E5 held-out indexing | 2.19 h for 14 documents (647 pages) | `experiments/frozen/e6/README.md` |
| Notebook 00 OCR | about a minute for 120 pages | notebook 00 (Interpretation, Limitations) |
| E8 full run | 354 sequential calls in 14 min 42 s | `docs/baseline_b1_specification.md` §7 |
| Final evaluation indexing | 5,554 pages of 110 documents on the M1 GPU in about 14 h, at about 9.5 s per page (mean 6.822 s vision + 2.597 s language model); 1,657 pages needed OCR | `docs/PROGRESS.md`; `experiments/frozen/final_index/index_summary.json` |
| Final evaluation embeddings | about 1 GB under `data/cache/final/`; pass-1 features take about 1.8 MB per page, so the two passes alternate over 200-page chunks to limit transient disk | `experiments/frozen/final_index/README.md`; notebook 09 (Method) |
| Final evaluation reader run | 2,079 calls from 12:44:11 to 14:35:16 UTC on 2026-11-26 | `experiments/frozen/final/PROVENANCE.json` |

`docs/application.md` quotes about 13 s per page for the application's encoder, the same two-pass procedure. Encoding stays on the M1 for bitwise parity with E5, so a datalab GPU would not be used to re-encode for these results (`docs/ssp_cloud.md`).

---

## 10. Test-pool rules

The **test pool** is every MMLongBench-Doc document outside the 20 used in development: 115 documents and 916 questions (`experiments/test_pool_ledger.md`). It stayed untouched until the approved final evaluation, which used it **once**, on 2026-11-26, on 110 documents and 872 questions (4 documents whose questions had been seen earlier and `mi_phone.pdf` excluded).

**How the one use was protected** (`experiments/specs/final_evaluation_v1.json`; commits in `docs/research_report.md` §9.1):
1. The specification was approved and frozen before any pool document was downloaded.
2. The PDFs were downloaded at the pinned revision and hash-verified; the index (page renders and embeddings) was built and **committed before any question was read**.
3. Only then were the questions loaded, encoded and ranked; the rankings and the call plan were frozen before any reader call.
4. One reader session, frozen configurations only, pre-registered claims only; deviations were committed before any result they could affect.

**Rules from now on.**
1. **Report it, never tune on it.** No configuration may be chosen, adjusted or adopted because of a pool result. A1's held-out gain is a reason for a new experiment on new data, not for changing B1 (`experiments/frozen/final/README.md`).
2. **No per-question error analysis on the pool**, beyond blind scoring adjudication of the 85 queued S-v2 items (`experiments/test_pool_ledger.md`, consequence 3).
3. **Record anything seen.** The ledger lists every piece of pool information displayed or used, by level, including the final evaluation's steps and one pool reference answer that was quoted in deviation D2's text after the run. Inspect table schemas by column names only.
4. **The application still refuses pool documents** by name (all 115 names) and, for one PDF, by SHA-256 (`docs/application.md` §4).
5. **Do not re-run notebook 09's paid modes.** A second reader session on the pool would be a second use.
