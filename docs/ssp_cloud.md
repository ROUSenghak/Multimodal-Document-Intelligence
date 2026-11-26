# Moving the project to an Onyxia datalab (ENSAE-ENSAI Datalab / SSP Cloud)

Both platforms run Onyxia and work the same way. The owner uses the **ENSAE-ENSAI Datalab**, whose storage endpoint is `minio-simple.lab.groupe-genes.fr` and whose bucket is `s3/<username>/`. On the public SSP Cloud the endpoint is `minio.lab.sspcloud.fr`. Always copy the endpoint and credentials from **My account → Connect to storage**, never from this guide.

This guide moves the project from the laptop to an SSP Cloud service. You lose no work and do not depend on any single service's disk.

## 0. What lives where

SSP Cloud services are temporary containers. The documentation warns that "for some services, deleting an instance will also delete all associated data, and this action is irreversible", and that inactive instances are sometimes removed. Use durable storage for everything you care about:

| What | Durable home | Notes |
|---|---|---|
| Code, notebooks, frozen experiments, specs, docs, `docs/PROGRESS.md` | **GitHub** (`origin`) | Push before you delete a service |
| Git-ignored data: caches, embeddings, page images, processed tables, run logs (about 3.4 GB) | **MinIO** (S3; "My Files"), under `s3/<your-username>/visualdoc/` | The access token lasts 7 days and is renewed automatically in new services |
| `OPENAI_API_KEY` | **My secrets** (Vault), injected as an environment variable | Never upload `.env` |
| The service disk (`~/work`) | **Nowhere durable** | Working copy only |

Do **not** move:
- **`.venv`.** Rebuild it on Linux.
- **`.env`.** The key goes to My secrets instead.
- **The 4.4 GB ColQwen2 weights.** They are re-downloadable, and needed only to re-encode.

SSP Cloud accepts only public, non-sensitive data. MMLongBench-Doc is a public benchmark (CC BY-NC 4.0).

**One rule that does not move.** Notebook 04's and notebook 09's *encoding* modes (`index`, `queries`) require the Apple M1 GPU (MPS). E5 encoded there, and the frozen specs require bit-for-bit equality with it; another GPU type gives slightly different numbers. Everything else reads the saved embeddings and runs anywhere:
- offline evaluation;
- the smoke and full reader runs;
- tests and the application.

Notebook 09 also uses **frozen rankings** (`experiments/frozen/final_retrieval/`). On another machine it only checks that recomputed scores are consistent with them, up to 1e-4.

## 1. On the laptop

1. **Finish the local steps** (done by Claude):
   - freeze and commit the index;
   - encode the questions on the M1 GPU;
   - freeze the rankings and the plan;
   - run the tests.
2. **Push to GitHub** (needs your approval):
   ```bash
   git push origin refactor/simplify-structure
   ```
3. **Configure MinIO on the laptop** (done 2026-11-26).
   1. Install the client: `brew install minio-mc`. The `minio/stable` tap points to a release that now returns HTTP 410.
   2. In the datalab, open **My account → Connect to storage** and choose **MC client**. Click the copy icon at the end of the `export MC_HOST_s3=https://…` line. **Never paste it into a chat or a screenshot:** it contains the secret key.
   3. Save it in a private file, in Terminal: `nano ~/.sspcloud_s3`; paste; **Ctrl+O**, **Enter**, **Ctrl+X**; then `chmod 600 ~/.sspcloud_s3`.
   4. Load it in any shell that needs it, without printing it:
      ```bash
      source ~/.sspcloud_s3 && mc ls s3/<your-username>/
      ```
      The credentials expire after about 2 weeks on the ENSAE-ENSAI Datalab and 7 days on SSP Cloud. Refresh the file from the same page.
4. **Upload the data.** `mc mirror` is resumable, so re-running it skips what is already there.

   **Exclude iCloud placeholders.** A file whose bytes are not on the Mac reads as empty and would be stored as an empty, corrupt copy. List them with `find data experiments/runs -type f -flags +dataless`. On 2026-11-26 the only ones were 9 development PDFs in `data/external/mmlongbench_doc/documents/`. They are re-downloadable from Hugging Face and verifiable by hash, so pass each one to `mc mirror` as `--exclude documents/<name>.pdf`.
   ```bash
   U=<your-username>
   for d in data/processed data/cache/final data/cache/e5 data/cache/mmlongbench_doc data/external/mmlongbench_doc/documents experiments/runs; do
     mc mirror --overwrite "$d" "s3/$U/visualdoc/$d"
   done
   mc du s3/$U/visualdoc/     # about 3.4 GB; compare file counts and bytes with the Mac before deleting anything
   ```

### What the upload achieved (2026-11-26, ENSAE-ENSAI Datalab)

| Folder | On MinIO | Notes |
|---|---|---|
| `data/cache/final` (test embeddings, 1.04 GB) | ✅ 6,223 files, bytes identical | irreplaceable (14 h of M1 encoding) |
| `data/cache/e5` (E5 embeddings) | ✅ 1,013 files, bytes identical | |
| `data/cache/mmlongbench_doc` (page images) | ❌ mostly blocked | |
| `data/external/mmlongbench_doc` (PDFs) | ❌ mostly blocked | |
| `data/processed` | ⚠️ 213 of 250 files | |
| `experiments/runs` | ⚠️ 452 of 453 files | |

**The storage gateway's filter rejected many uploads with an HTML block page.**
- **It filters content, not size.** Random files of 1–3 MB pass. Some ordinary CSV, parquet and log files, PDFs and some PNGs are rejected, consistently. A 20 MB file was also rejected.
- **Do not try to disguise the files** (for example by encrypting them). That would circumvent the school's security control.
- **Legitimate routes:**
  1. **Report the false positives** to the Datalab administrators.
  2. **Rebuild inside a Datalab service.**
     - Re-download the PDFs from Hugging Face. Notebook 09's download cell checks each one against the pinned revision's hash.
     - Re-render the pages, and check them against the frozen manifest's image hashes.
     - Re-run the notebooks offline to regenerate the processed tables.

**Do not delete the Mac copy** until one of these routes has succeeded and been verified.

## 2. On SSP Cloud

1. **My secrets** (left menu of the datalab):
   1. Create a folder `visualdoc` (**+ New folder**).
   2. Add the secret `OPENAI_API_KEY` = your key (**+ New secret**, then **+ Add a variable**).
   3. Click **Use in a service** to copy its path.
2. **GitHub token.**
   1. Create one at <https://github.com/settings/tokens> with scope `repo` and a short expiry (30 days).
   2. Add it to your account's **External services**. Set your account email to your GitHub email.
3. **Launch a service** from the catalog: `vscode-python` or `jupyter-python`. A CPU is enough; a GPU only matters for encoding, which stays on the M1. In the configuration:
   - **Git** tab: repository `https://github.com/ROUSenghak/Multimodal-Document-Intelligence.git`, branch `refactor/simplify-structure`;
   - **Vault** tab: paste the secret's path;
   - **Resources**: a disk of at least 20 GB.
4. **In the service terminal:**
   ```bash
   cd ~/work/Multimodal-Document-Intelligence
   echo ${OPENAI_API_KEY:+key present}          # never print the key itself
   python3 --version                            # 3.12 or later is required
   python3 -m venv .venv && source .venv/bin/activate
   pip install --upgrade pip
   pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu   # CPU build: much smaller than the CUDA one
   pip install -r requirements/lock-2026-11-26.txt
   pip install -e . --no-deps
   python -m ipykernel install --user --name visualdoc-venv --display-name "VisualDoc (.venv, Python 3.12)"
   U=<your-username>
   for d in data/processed data/cache/final data/cache/e5 data/cache/mmlongbench_doc data/external/mmlongbench_doc/documents experiments/runs; do
     mc mirror --overwrite "s3/$U/visualdoc/$d" "$d"
   done
   ```
   `mc` is preinstalled in SSP Cloud services, with the alias `s3` already configured.
5. **Check that the move is complete and intact:**
   ```bash
   for d in experiments/frozen/*/; do (cd "$d" && sha256sum -c --quiet SHA256SUMS) || echo "MISMATCH in $d"; done
   PYTHONPATH=src python -m pytest -q
   jupyter nbconvert --to notebook --execute --output /tmp/nb09_check.ipynb notebooks/09_final_evaluation.ipynb
   ```
   The notebook 09 check should report:
   - "Index frozen and committed: True";
   - question embeddings complete;
   - frozen rankings consistent;
   - the plan frozen;
   - "Paid gate closed".

### 2.6 The rebuild test: can the Datalab re-create what the storage filter blocked?

Run this in your first service. It answers whether the PDFs, page images and page texts can be re-created identically on the Datalab. If they can, nothing more needs uploading, and the Mac copy can be deleted afterwards.

1. **Install the minimum.** In the service terminal, inside the cloned repository:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install pymupdf==2.1 pandas pyarrow huggingface_hub certifi ipykernel
   python -m ipykernel install --user --name visualdoc-venv --display-name "VisualDoc (.venv, Python 3.12)"
   ```
   - **`pymupdf==2.1` must match exactly:** the renderer's version decides the page bytes.
   - **No separate OCR program is needed.** Tesseract is built into PyMuPDF and uses the language file `resources/tessdata/eng.traineddata` from the repository. This was checked on 2026-11-26 with no `tesseract` program available.
2. **Run the test.** Open a notebook on the `visualdoc-venv` kernel, with the working directory set to the repository root, and paste the code below into one cell.
   - It downloads about 0.6 GB (124 PDFs) and checks every PDF against the pinned revision's hash.
   - For 3 pages per document, it compares the re-rendered image and the re-extracted text (with OCR where needed) with the frozen hashes.
   - It takes about 10–20 minutes.
3. **Check whether the filter applies from inside the Datalab.** This file was blocked from the Mac:
   ```bash
   mc cp data/external/mmlongbench_doc/documents/0b85477387a9d0cc33fca0f4becaa0e5.pdf s3/<your-username>/visualdoc/_filtertest/ && echo "inside: upload OK"
   mc rm --recursive --force s3/<your-username>/visualdoc/_filtertest
   ```
4. **Read the summary.** The last four lines give the counts and the verdict.
   - **"REBUILD WORKS"**: everything can be re-created here.
   - **"NOT IDENTICAL"**: keep the Mac copy, and paste the rows that differ.

```python
"""Datalab rebuild test (run from the repository root). Answers one question: can this machine rebuild the PDFs and page
images that the storage filter blocked, identical to the frozen ones? Downloads PDFs, verifies each against the hash
recorded at the pinned revision, re-renders sample pages and compares them with the frozen manifests. No API call.

Environment variables: TARGET (download folder, default data/external/mmlongbench_doc/documents), LIMIT (documents, default all),
PAGES_PER_DOC (sample renders per document, default 3)."""
import hashlib
import os
import shutil
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

import certifi
import pandas as pd
import pymupdf
from huggingface_hub import HfApi, hf_hub_download

REPO, REVISION = "yubo2333/MMLongBench-Doc", "2ff6aa9237fc777b6627dc57a486e9225ac5fb86"
TARGET = Path(os.environ.get("TARGET", "data/external/mmlongbench_doc/documents"))
LIMIT = int(os.environ.get("LIMIT", "0")) or None
PAGES_PER_DOC = int(os.environ.get("PAGES_PER_DOC", "3"))
TARGET.mkdir(parents=True, exist_ok=True)


def local_hash(path, kind):
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest() if kind == "sha256" else hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def page_text(page):  # notebook 00/09 rule: native text, or full-page OCR (eng, 150 dpi) below 30 native words
    native = page.get_text("text", sort=True)
    if len(native.split()) >= 30:
        return native
    textpage = page.get_textpage_ocr(language="eng", dpi=150, full=True, tessdata="resources/tessdata")
    return page.get_text("text", textpage=textpage, sort=True)


def render(page):  # notebook 09 / E1 profile: whole page fitted in 768 x 1536 px, RGB PNG
    zoom = min(768 / min(page.rect.width, page.rect.height), 1536 / max(page.rect.width, page.rect.height))
    return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).tobytes("png")


# The documents and their frozen page hashes: the 110 evaluation documents and the 14 held-out development documents.
pool = pd.read_csv("experiments/frozen/final_index/pool_documents.csv").query("verified")
texts = pd.read_csv("experiments/frozen/final_index/index_manifest.csv").set_index(["doc_id", "page"])["text_sha256"]
manifest = pd.concat([pd.read_csv("experiments/frozen/final_index/index_manifest.csv")[["doc_id", "page", "sha256"]],
                      pd.read_csv("experiments/frozen/e5/tables/render_manifest_heldout.csv")[["doc_id", "page", "sha256"]]])
docs = sorted(pool["doc_id"]) + sorted(set(manifest["doc_id"]) - set(pool["doc_id"]))
docs = docs[:LIMIT]
items = {}
for start in range(0, len(docs), 50):
    items.update({Path(i.path).name: i for i in HfApi().get_paths_info(REPO, [f"documents/{d}" for d in docs[start:start + 50]],
                                                                       repo_type="dataset", revision=REVISION)})
tls = ssl.create_default_context(cafile=certifi.where())
rows = []
for doc in docs:
    item, path = items[doc], TARGET / doc
    kind, expected = ("sha256", item.lfs.sha256) if item.lfs else ("git-blob-sha1", item.blob_id)
    status = "ok" if path.is_file() and path.stat().st_size and local_hash(path, kind) == expected else None
    if status is None:
        try:
            hf_hub_download(REPO, f"documents/{doc}", repo_type="dataset", revision=REVISION, local_dir=TARGET.parent, force_download=True)
        except OSError:
            pass
        if not (path.is_file() and local_hash(path, kind) == expected):  # direct fetch, kept only if the hash matches
            url = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/documents/{urllib.parse.quote(doc)}"
            tmp = path.with_name(f".{path.name}.tmp")
            with urllib.request.urlopen(url, timeout=300, context=tls) as response, open(tmp, "wb") as handle:
                shutil.copyfileobj(response, handle)
            if local_hash(tmp, kind) == expected:
                os.replace(tmp, path)
            else:
                tmp.unlink()
        status = "ok" if path.is_file() and local_hash(path, kind) == expected else "HASH MISMATCH"
    renders = same = text_checked = text_same = 0
    if status == "ok":
        frozen = manifest[manifest["doc_id"] == doc].set_index("page")["sha256"]
        with pymupdf.open(path) as pdf:
            n = pdf.page_count
            sample = sorted({1, max(1, n // 2), n})[:PAGES_PER_DOC] if PAGES_PER_DOC < n else range(1, n + 1)
            for p in sample:
                renders += 1
                same += hashlib.sha256(render(pdf[p - 1])).hexdigest() == frozen.get(p)
                if (doc, p) in texts.index:  # page text (with OCR where needed): the frozen hash exists for evaluation documents
                    text_checked += 1
                    text_same += hashlib.sha256(page_text(pdf[p - 1]).encode()).hexdigest() == texts[(doc, p)]
    rows.append({"doc_id": doc, "pdf": status, "renders": renders, "identical": same, "texts": text_checked, "texts_identical": text_same})
    print(f"{len(rows):3d}/{len(docs)} {doc[:46]:46s} pdf {status:13s} renders {same}/{renders} texts {text_same}/{text_checked}", flush=True)

table = pd.DataFrame(rows)
print("\n=== REBUILD TEST SUMMARY ===")
print(f"PDFs verified against the pinned revision: {(table['pdf'] == 'ok').sum()}/{len(table)}")
print(f"Re-rendered pages identical to the frozen hashes: {table['identical'].sum()}/{table['renders'].sum()}")
print(f"Re-extracted page texts (with OCR) identical to the frozen hashes: {table['texts_identical'].sum()}/{table['texts'].sum()}")
ok = (table["pdf"] == "ok").all() and table["identical"].sum() == table["renders"].sum() and table["texts_identical"].sum() == table["texts"].sum()
print("Verdict:", "REBUILD WORKS: PDFs, page images and page texts can be re-created here" if ok
      else "NOT IDENTICAL: keep the Mac copy; see the rows above")
```

### 2.7 Pausing and resuming a VS Code service without redoing the setup

**What survives.** A paused or restarted service keeps only **`/home/onyxia/work`**: the repository, its `.venv`, data and results. Deleting the service erases even that. Everything else in the home folder is recreated empty:
- Claude Code, with its login, chat history and memory;
- the VS Code extensions;
- the Jupyter kernel registration.

Confirm this once:
1. Run `echo test > ~/work/keep.txt; echo test > ~/outside.txt`.
2. Pause, then resume the service.
3. Run `ls ~/work/keep.txt ~/outside.txt`. Only the first file should remain.

**`tools/datalab_init.sh` restores the rest at every start:**
- it links `~/.claude` and `~/.claude.json` to `~/work`, so chat, memory and login persist;
- it installs Claude Code once into `~/work/.npm-global`, with no sudo needed, and puts it on `PATH`;
- it reinstalls the Python and Jupyter extensions for VS Code;
- it re-registers the `visualdoc-venv` kernel.

**Set it once, in the service configuration**, in the tab with the init settings (in Onyxia, the field is named `personalInit`):

```
https://raw.githubusercontent.com/ROUSenghak/Multimodal-Document-Intelligence/refactor/simplify-structure/tools/datalab_init.sh
```

**After a start, check the log:** `cat ~/work/.datalab_init.log`.
- If it says "npm not found", install Claude Code once by hand, following its documentation. Its files then live in `~/work` and survive.
- Log in to Claude Code the first time. The login is kept in `~/work/.claude`.

The script was tested on the Mac in a sandbox home, run twice to check that a second run changes nothing, but not yet on Onyxia. The log shows what each step did.

## 3. Continuing the final evaluation there

The remaining stages are the paid smoke and full runs, then the evaluation. They need no GPU:

```bash
VISUALDOC_FINAL_MODE=smoke jupyter nbconvert --to notebook --execute --output /tmp/nb09_smoke.ipynb notebooks/09_final_evaluation.ipynb
VISUALDOC_FINAL_MODE=full  jupyter nbconvert --to notebook --execute --output /tmp/nb09_full.ipynb --ExecutePreprocessor.timeout=-1 notebooks/09_final_evaluation.ipynb
```

The full run is about 2,100 calls and takes about 2.5 hours. It is resumable with `VISUALDOC_FINAL_RUN_ID=<run id>` if interrupted. Use the owner-approved ceiling only; the notebook enforces $2.50.

To work with Claude Code in the service:
1. Install it with `npm install -g @anthropic-ai/claude-code`.
2. Run `claude` in the project folder.
3. Optionally copy the memory notes from the laptop's `~/.claude/projects/<project-key>/memory/` into the matching folder under the service's `~/.claude/projects/`. They are a convenience; `docs/PROGRESS.md` is the project's own record.

## 4. Before you delete or leave a service

```bash
git add -A && git commit -m "..." && git push            # code, notebooks, frozen packages
U=<your-username>
for d in data/processed data/cache/final experiments/runs; do mc mirror --overwrite "$d" "s3/$U/visualdoc/$d"; done
```

Only then delete the service. A new service with the same configuration, followed by step 2.4, brings everything back.
