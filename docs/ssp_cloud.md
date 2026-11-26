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
