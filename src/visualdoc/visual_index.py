"""Visual page index for B1: ColQwen2 page embeddings, stored per document, scored by MaxSim.

B1 retrieves with ColQwen2 v1.0 (E5: evidence recall after the guard 0.526 -> 0.721;
E6: 25/102 -> 38/102 answers). Scoring is already in the pinned application module
``retrieval`` (``CachedVisualIndex`` / ``maxsim_score``, NumPy, no model). This module
supplies what scoring needs and the application did not have:

1. **A persistent embedding store.** One safetensors file per document holds one
   matrix per page (tokens x 128, bfloat16), under the key

       (PDF SHA-256, render profile, model id, model revision)

   The key is written inside the file and checked on every load: an embedding made
   for another PDF, another rendering or another checkpoint is refused, never reused.
   Writes are atomic (temporary file, fsync, rename).
2. **A query-embedding cache**, keyed by (model id, revision, SHA-256 of the exact question).
3. **An importer** for the embeddings notebook 04 (E5) already computed, so the
   development documents get a visual index without loading the model.
4. **The live ColQwen2 encoder** (``ColQwen2Encoder``), ported from notebook 04's
   two-pass encoding, which E5 checked to be bitwise identical to the single pass
   and which fits an 8-GB machine. torch and transformers are imported only inside it.
   NOT EXECUTED IN TESTS: the 4.4 GB checkpoint is not available on the development
   machine; the tests run its orchestration on a small fake model.

The safetensors format is written and read here with NumPy alone, because NumPy has no
bfloat16 type (the ``safetensors.numpy`` loader refuses BF16). A file is::

    8-byte little-endian header length | JSON header (padded with spaces to 8 bytes) | raw tensor bytes

bfloat16 is the upper half of a float32 (same sign and exponent, 7 mantissa bits), so
widening it to float32 is exact: ``float32 bits = bf16 bits << 16``.
"""

import csv
import gc
import hashlib
import io
import json
import os
import re
import struct
import sys
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from math import prod
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from .documents import IMAGE_LONG_SIDE_PX, IMAGE_SHORT_SIDE_PX, open_pdf, render_pages, sha256_file

REPO_ROOT = Path(__file__).resolve().parents[2]

# The checkpoint frozen by the E5 spec (experiments/specs/e5_visual_retrieval_v1.json).
COLQWEN2_MODEL_ID = "vidore/colqwen2-v1.0-hf"
COLQWEN2_REVISION = "ddc07d2317c80f75fc742b7362ee9ad1912908f9"
COLQWEN2_WEIGHTS_BYTES = 4_418_454_832
DEFAULT_MODEL_DIR = REPO_ROOT / "data" / "cache" / "hf" / f"colqwen2-v1.0-hf@{COLQWEN2_REVISION[:12]}"
EMBEDDING_DIM = 128
# The page images the reader sees (documents.render_pages): the E1 profile. ColQwen2 encodes the same PNGs.
RENDER_PROFILE = f"short{IMAGE_SHORT_SIDE_PX}-long{IMAGE_LONG_SIDE_PX}"
STORE_FORMAT = "visualdoc-visual-index-v1"

# macOS marks iCloud files whose bytes are not on disk with this st_flags bit (SF_DATALESS in <sys/stat.h>).
# Reading such a file downloads it, so availability is decided from os.stat alone.
SF_DATALESS = 0x40000000

_SAFETENSORS_ITEMSIZE = {"BF16": 2, "F32": 4}
_MAX_HEADER_BYTES = 100_000_000


class IndexKeyMismatch(ValueError):
    """A stored embedding was computed under a different key than the one requested."""


# --- bfloat16 <-> float32 ------------------------------------------------------------------------


def bf16_bits_to_float32(bits: Any) -> np.ndarray:
    """Widen bfloat16 bit patterns (uint16) to float32. Exact: the 16 bits become the float32's upper half."""
    return (np.asarray(bits, dtype=np.uint16).astype(np.uint32) << 16).view(np.float32)


def float32_to_bf16_bits(values: Any) -> np.ndarray:
    """Round float32 values to the nearest bfloat16 (ties to even) and return the uint16 bit patterns.

    A value that came out of a bf16 model is already a bfloat16 number, so it converts back
    without any change; that is what makes the store lossless for ColQwen2 embeddings.
    """
    values = np.ascontiguousarray(values, dtype=np.float32)
    if not np.isfinite(values).all():
        raise ValueError("embeddings must be finite numbers")
    bits = values.view(np.uint32)
    # Add 0x7FFF, plus 1 when the kept part is odd, then drop the lower 16 bits: round half to even.
    rounding = ((bits >> 16) & np.uint32(1)) + np.uint32(0x7FFF)
    return ((bits + rounding) >> 16).astype(np.uint16)


# --- safetensors bytes (NumPy only) ----------------------------------------------------------------


def encode_safetensors(tensors: Mapping[str, Any], metadata: Mapping[str, str] | None = None) -> bytes:
    """Serialise float matrices as BF16 safetensors, laid out as the safetensors library lays them out.

    Tensors are written in name order; ``__metadata__`` (string -> string) comes first in the header.
    """
    header: dict[str, Any] = {}
    if metadata:
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in metadata.items()):
            raise TypeError("safetensors metadata must map strings to strings")
        header["__metadata__"] = dict(sorted(metadata.items()))
    chunks, offset = [], 0
    for name in sorted(tensors):
        if name == "__metadata__":
            raise ValueError("'__metadata__' is reserved")
        array = np.asarray(tensors[name])
        data = float32_to_bf16_bits(array).astype("<u2").tobytes()
        header[name] = {"dtype": "BF16", "shape": list(array.shape), "data_offsets": [offset, offset + len(data)]}
        chunks.append(data)
        offset += len(data)
    text = json.dumps(header, separators=(",", ":")).encode()
    text += b" " * (-len(text) % 8)  # the library pads the header to a multiple of 8 bytes
    return struct.pack("<Q", len(text)) + text + b"".join(chunks)


def decode_safetensors(raw: bytes) -> tuple[dict[str, np.ndarray], dict[str, str]]:
    """(float32 tensors, metadata) from safetensors bytes holding BF16 or F32 tensors; malformed files raise ValueError."""
    if len(raw) < 8:
        raise ValueError("not a safetensors file: shorter than its 8-byte header length")
    (header_length,) = struct.unpack("<Q", raw[:8])
    if header_length > min(_MAX_HEADER_BYTES, len(raw) - 8):
        raise ValueError("not a safetensors file: header length out of range")
    try:
        header = json.loads(raw[8:8 + header_length])
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"not a safetensors file: unreadable header ({error})") from error
    if not isinstance(header, dict):
        raise ValueError("not a safetensors file: the header is not a JSON object")
    metadata = header.pop("__metadata__", None) or {}
    if not isinstance(metadata, dict) or not all(isinstance(v, str) for v in metadata.values()):
        raise ValueError("safetensors metadata must map strings to strings")
    data = memoryview(raw)[8 + header_length:]

    tensors, spans = {}, []
    for name, info in header.items():
        try:
            dtype, shape, (start, end) = info["dtype"], info["shape"], info["data_offsets"]
        except (TypeError, KeyError, ValueError) as error:
            raise ValueError(f"tensor {name!r}: malformed header entry") from error
        if dtype not in _SAFETENSORS_ITEMSIZE:
            raise ValueError(f"tensor {name!r}: dtype {dtype} is not supported (BF16 or F32)")
        if not isinstance(shape, list) or not all(isinstance(n, int) and n >= 0 for n in shape):
            raise ValueError(f"tensor {name!r}: invalid shape {shape!r}")
        if not (isinstance(start, int) and isinstance(end, int) and 0 <= start <= end <= len(data)):
            raise ValueError(f"tensor {name!r}: data offsets outside the file")
        if end - start != prod(shape) * _SAFETENSORS_ITEMSIZE[dtype]:
            raise ValueError(f"tensor {name!r}: {end - start} bytes do not hold a {dtype} tensor of shape {shape}")
        values = np.frombuffer(data[start:end], dtype="<u2" if dtype == "BF16" else "<f4").reshape(shape)
        tensors[name] = bf16_bits_to_float32(values) if dtype == "BF16" else values.astype(np.float32)
        spans.append((start, end))
    # The tensors must tile the data section exactly: no gap, no overlap, nothing left over.
    position = 0
    for start, end in sorted(spans):
        if start != position:
            raise ValueError("safetensors data section has a gap or an overlap")
        position = end
    if position != len(data):
        raise ValueError("safetensors data section has trailing bytes")
    return tensors, metadata


def atomic_write_bytes(path: str | Path, data: bytes) -> None:
    """Write a temporary file next to the target, fsync it, then rename it over the target.

    ``os.replace`` is atomic on one filesystem: after an interruption the target is absent,
    its previous version or the complete new file, never a partial one (notebook 04's rule).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")  # hidden: never matches "*.safetensors"
    try:
        with open(temporary, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)  # only left behind when the write or rename failed


def validate_embedding(matrix: Any, what: str) -> np.ndarray:
    """A (tokens, 128) float matrix with at least one token and finite values, as float32."""
    matrix = np.asarray(matrix, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] < 1 or matrix.shape[1] != EMBEDDING_DIM:
        raise ValueError(f"{what}: expected a (tokens >= 1, {EMBEDDING_DIM}) matrix, got shape {matrix.shape}")
    if not np.isfinite(matrix).all():
        raise ValueError(f"{what}: embeddings must be finite numbers")
    return matrix


# --- the store ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class IndexKey:
    """What a document's page embeddings depend on; all four parts must match before they are reused."""

    pdf_sha256: str
    render_profile: str = RENDER_PROFILE
    model_id: str = COLQWEN2_MODEL_ID
    model_revision: str = COLQWEN2_REVISION

    def __post_init__(self):
        if not re.fullmatch(r"[0-9a-f]{64}", self.pdf_sha256):
            raise ValueError(f"pdf_sha256 must be 64 lower-case hex digits, got {self.pdf_sha256!r}")
        if not re.fullmatch(r"short\d+-long\d+", self.render_profile):
            raise ValueError(f"render_profile must look like 'short768-long1536', got {self.render_profile!r}")
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", self.model_id):
            raise ValueError(f"model_id must be a Hugging Face 'owner/name', got {self.model_id!r}")
        if not re.fullmatch(r"[0-9a-f]{40}", self.model_revision):
            raise ValueError("model_revision must be a full 40-hex commit, so a moving branch cannot hide a change")


def query_sha256(question: str) -> str:
    """Query cache key: the exact question text (E5's rule). Any change in the text is a different query."""
    return hashlib.sha256(str(question).encode()).hexdigest()


def _page_name(page: int) -> str:
    return f"page_{page:04d}"  # zero-padded, so name order is page order


class VisualIndexStore:
    """Page and query embeddings on disk.

    Layout under ``root``::

        <owner>--<name>@<revision[:12]>/<render profile>/<pdf sha256>.safetensors   one file per document
        <owner>--<name>@<revision[:12]>/queries/<question sha256>.safetensors       one file per question
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _model_dir(self, model_id: str, model_revision: str) -> Path:
        return self.root / f"{model_id.replace('/', '--')}@{model_revision[:12]}"

    def path(self, key: IndexKey) -> Path:
        return self._model_dir(key.model_id, key.model_revision) / key.render_profile / f"{key.pdf_sha256}.safetensors"

    def has(self, key: IndexKey) -> bool:
        return self.path(key).is_file()

    def save(
        self,
        key: IndexKey,
        pages: Mapping[int, Any],
        *,
        png_sha256: Mapping[int, str],
        encoder: Mapping[str, Any] | None = None,
    ) -> Path:
        """Store every page of one document (pages 1..N, no gap), atomically, with its key inside the file."""
        numbers = sorted(pages)
        if not numbers or numbers != list(range(1, len(numbers) + 1)) or any(isinstance(p, bool) for p in numbers):
            raise ValueError(f"pages must be numbered 1..N without gaps, got {numbers[:5]}...")
        if sorted(png_sha256) != numbers or not all(re.fullmatch(r"[0-9a-f]{64}", png_sha256[p]) for p in numbers):
            raise ValueError("png_sha256 must give the 64-hex SHA-256 of every page image")
        tensors = {_page_name(p): validate_embedding(pages[p], f"page {p}") for p in numbers}
        metadata = {
            **asdict(key),
            "format": STORE_FORMAT,
            "page_count": str(len(numbers)),
            "png_sha256": json.dumps([png_sha256[p] for p in numbers]),
            "encoder": json.dumps(dict(encoder or {}), sort_keys=True, default=str),
        }
        path = self.path(key)
        atomic_write_bytes(path, encode_safetensors(tensors, metadata))
        return path

    def load(self, key: IndexKey) -> dict[int, np.ndarray] | None:
        """{page: float32 (tokens, 128)} for this key, None when absent; IndexKeyMismatch if the file says otherwise."""
        path = self.path(key)
        if not path.is_file():
            return None
        tensors, metadata = decode_safetensors(path.read_bytes())
        for field, expected in asdict(key).items():
            if metadata.get(field) != expected:
                raise IndexKeyMismatch(
                    f"{path.name} was stored for {field}={metadata.get(field)!r}, not the requested {expected!r}; "
                    "refusing to reuse embeddings computed under another key"
                )
        if metadata.get("format") != STORE_FORMAT:
            raise ValueError(f"{path.name}: unknown store format {metadata.get('format')!r}")
        count = int(metadata.get("page_count", "0"))
        if sorted(tensors) != [_page_name(p) for p in range(1, count + 1)]:
            raise ValueError(f"{path.name}: page tensors do not match its page count {count}")
        return {p: validate_embedding(tensors[_page_name(p)], f"{path.name} page {p}") for p in range(1, count + 1)}

    def stored_png_sha256(self, key: IndexKey) -> list[str]:
        """The SHA-256 of each page image the stored embeddings were computed from (audit trail)."""
        _, metadata = decode_safetensors(self.path(key).read_bytes())
        return json.loads(metadata["png_sha256"])

    def query_path(self, question_sha256: str, model_id: str = COLQWEN2_MODEL_ID, model_revision: str = COLQWEN2_REVISION) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", question_sha256):
            raise ValueError("a query key is a 64-hex SHA-256")
        return self._model_dir(model_id, model_revision) / "queries" / f"{question_sha256}.safetensors"

    def save_query(self, question_sha256: str, embedding: Any, *, model_id: str = COLQWEN2_MODEL_ID,
                   model_revision: str = COLQWEN2_REVISION) -> Path:
        path = self.query_path(question_sha256, model_id, model_revision)
        metadata = {"format": STORE_FORMAT, "query_sha256": question_sha256, "model_id": model_id, "model_revision": model_revision}
        atomic_write_bytes(path, encode_safetensors({"embedding": validate_embedding(embedding, "query")}, metadata))
        return path

    def load_query(self, question_sha256: str, *, model_id: str = COLQWEN2_MODEL_ID,
                   model_revision: str = COLQWEN2_REVISION) -> np.ndarray | None:
        path = self.query_path(question_sha256, model_id, model_revision)
        if not path.is_file():
            return None
        tensors, metadata = decode_safetensors(path.read_bytes())
        expected = {"query_sha256": question_sha256, "model_id": model_id, "model_revision": model_revision}
        for field, value in expected.items():
            if metadata.get(field) != value:
                raise IndexKeyMismatch(f"{path.name} was stored for {field}={metadata.get(field)!r}, not {value!r}")
        return validate_embedding(tensors.get("embedding"), f"query {question_sha256[:12]}")


# --- importing notebook 04's (E5) cache ----------------------------------------------------------------


def read_e5_config(e5_dir: str | Path) -> dict:
    """The E5 cache's encoder configuration, after checking it is the model, dtype and rendering B1 uses."""
    e5_dir = Path(e5_dir)
    config_path = e5_dir / "config.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"no E5 embedding cache at {e5_dir} (notebook 04 writes it)")
    config = json.loads(config_path.read_text())
    expected = {"repo": COLQWEN2_MODEL_ID, "revision": COLQWEN2_REVISION, "dtype": "bfloat16"}
    for field, value in expected.items():
        if config.get(field) != value:
            raise IndexKeyMismatch(f"E5 cache {e5_dir.name} has {field}={config.get(field)!r}, B1 needs {value!r}")
    if f"{IMAGE_SHORT_SIDE_PX} x {IMAGE_LONG_SIDE_PX}" not in str(config.get("page_image")):
        raise IndexKeyMismatch(f"E5 cache {e5_dir.name} encoded pages under {config.get('page_image')!r}, not {RENDER_PROFILE}")
    return config


def _read_e5_embedding(path: Path) -> np.ndarray:
    tensors, _ = decode_safetensors(path.read_bytes())
    return validate_embedding(tensors.get("embedding"), path.name)


ARCHIVED_PAGES_FILE = REPO_ROOT / "resources" / "archived_page_images.json"


def _png_size(png: bytes) -> tuple[int, int]:
    """(width, height) from a PNG's IHDR chunk."""
    if png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
        raise ValueError("not a PNG file")
    return struct.unpack(">II", png[16:24])


def _frozen_manifest_sha256(manifest: Path) -> dict[tuple[str, int], tuple[str, str]]:
    """{(doc_id, page): (sha256, image_path)} of a frozen render manifest, after checking it against its package's SHA256SUMS."""
    package = manifest.parent.parent
    sums = dict(line.split()[::-1] for line in (package / "SHA256SUMS").read_text().splitlines() if line.strip())
    relative = manifest.relative_to(package).as_posix()
    if relative not in sums or hashlib.sha256(manifest.read_bytes()).hexdigest() != sums[relative]:
        raise IndexKeyMismatch(f"{manifest} does not match {package.name}/SHA256SUMS; refusing archived page images")
    with manifest.open(newline="") as handle:
        return {(row["doc_id"], int(row["page"])): (row["sha256"], row["image_path"]) for row in csv.DictReader(handle)}


def verified_archived_pages(pdf_path: str | Path, pages: list[int], rendered: Mapping[int, bytes], *,
                            records_file: str | Path = ARCHIVED_PAGES_FILE, root: str | Path = REPO_ROOT) -> dict[int, dict]:
    """Archived E5 page images allowed to replace fresh renders of ``pages``, after checking their provenance.

    Only pages listed in ``records_file`` (a reviewed, committed list) qualify. For each one the
    PDF's SHA-256, the frozen render manifest (against its package's SHA256SUMS), the archived
    PNG's bytes and its pixel size (against the fresh render's) must all agree, or IndexKeyMismatch
    is raised. Returns {page: {"png_sha256", "rendered_png_sha256", "image_path"}} for the listed pages.
    """
    root, name = Path(root), Path(pdf_path).name
    records = json.loads(Path(records_file).read_text())["pages"] if Path(records_file).is_file() else []
    listed = {record["page"]: record for record in records if record["doc_id"] == name and record["page"] in pages}
    if not listed:
        return {}
    pdf_sha = sha256_file(pdf_path)
    accepted = {}
    for page, record in sorted(listed.items()):
        what = f"{name} page {page}"
        if record["pdf_sha256"] != pdf_sha:
            raise IndexKeyMismatch(f"{what}: the archived image was recorded for PDF {record['pdf_sha256'][:12]}, not {pdf_sha[:12]}")
        frozen = _frozen_manifest_sha256(root / record["frozen_manifest"]).get((name, page))
        if frozen != (record["archived_png_sha256"], record["image_path"]):
            raise IndexKeyMismatch(f"{what}: the frozen manifest records {frozen}, not the archived image's hash and path")
        image = root / record["image_path"]
        if not image.is_file():
            raise FileNotFoundError(f"{what}: archived image {record['image_path']} absent (restore it from the archive)")
        png = image.read_bytes()
        if hashlib.sha256(png).hexdigest() != record["archived_png_sha256"]:
            raise IndexKeyMismatch(f"{what}: archived image bytes do not match their recorded SHA-256")
        if _png_size(png) != _png_size(rendered[page]):
            raise IndexKeyMismatch(f"{what}: archived image is {_png_size(png)}, the fresh render {_png_size(rendered[page])}")
        accepted[page] = {"png_sha256": record["archived_png_sha256"], "image_path": record["image_path"],
                          "rendered_png_sha256": hashlib.sha256(rendered[page]).hexdigest()}
    return accepted


def import_e5_document(pdf_path: str | Path, e5_dir: str | Path, store: VisualIndexStore) -> IndexKey:
    """Copy E5's page embeddings of one PDF into the store under the document key.

    E5 keyed each page by the SHA-256 of its 768-px PNG. The pages are rendered here with
    ``documents.render_pages`` and looked up by that hash, so an embedding is imported only
    for exactly the image B1 would encode (E5 checked that cached images equal fresh renders).

    Exception: on another processor PyMuPDF can render a few pages with different bytes than the
    M1 did. A page whose render has no E5 embedding may use E5's archived image instead, only if
    ``verified_archived_pages`` accepts it; the store records which pages were imported this way.
    """
    e5_dir = Path(e5_dir)
    config = read_e5_config(e5_dir)
    with open_pdf(pdf_path) as document:
        page_count = document.page_count
    images = render_pages(pdf_path, list(range(1, page_count + 1)))
    png_sha = {page: hashlib.sha256(png).hexdigest() for page, png in images.items()}
    files = {page: e5_dir / "pages" / f"{digest}.safetensors" for page, digest in png_sha.items()}
    missing = [page for page, path in files.items() if not path.is_file()]
    archived = verified_archived_pages(pdf_path, missing, images) if missing else {}
    for page, record in archived.items():
        png_sha[page] = record["png_sha256"]
        files[page] = e5_dir / "pages" / f"{record['png_sha256']}.safetensors"
    missing = [page for page, path in files.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            f"the E5 cache has no embedding for {len(missing)} of {page_count} pages of {Path(pdf_path).name} "
            f"(first: {missing[:5]}); only the 20 development documents were encoded in E5"
        )
    key = IndexKey(sha256_file(pdf_path))
    config_hash = e5_dir.name
    encoder = {"source": f"E5 cache {config_hash}", **{k: config.get(k) for k in ("device", "torch", "transformers")}}
    if archived:
        encoder["archived_page_images"] = {str(page): record for page, record in archived.items()}
    store.save(key, {page: _read_e5_embedding(path) for page, path in files.items()}, png_sha256=png_sha, encoder=encoder)
    return key


def import_e5_queries(e5_dir: str | Path, store: VisualIndexStore) -> int:
    """Copy every cached E5 query embedding (keyed, as here, by the SHA-256 of the question). Returns the count."""
    e5_dir = Path(e5_dir)
    read_e5_config(e5_dir)
    count = 0
    for path in sorted((e5_dir / "queries").glob("*.safetensors")):
        store.save_query(path.stem, _read_e5_embedding(path))
        count += 1
    return count


# --- query encoding at question time -----------------------------------------------------------------


class StoreQueryEncoder:
    """The ``query_encoder`` given to ``retrieval.CachedVisualIndex``.

    It answers from the store's query cache first. On a miss it uses the live encoder if
    one was enabled, and caches the result; otherwise it raises RuntimeError, which
    ``pipeline.answer_question_b1`` records as the reason for its BM25 fallback.
    """

    def __init__(self, store: VisualIndexStore, live_encoder: Any | None = None):
        self.store, self.live_encoder = store, live_encoder

    def __call__(self, question: str) -> np.ndarray:
        key = query_sha256(question)
        cached = self.store.load_query(key)
        if cached is not None:
            return cached
        if self.live_encoder is None:
            raise RuntimeError(
                "no cached ColQwen2 embedding for this question and the live encoder is off "
                "(start the app with --load-encoder to load the 4.4 GB checkpoint)"
            )
        embedding = validate_embedding(self.live_encoder.encode_query(question), "query")
        self.store.save_query(key, embedding)
        return embedding


# --- the live encoder (notebook 04, two passes) -------------------------------------------------------

# The encoder identity E5 recorded (data/cache/e5/<...>/config.json and the E5 spec). A test checks these
# values against that config.json. Any difference is a new condition: the encoder refuses to run, and the
# app then falls back to BM25 with the reason recorded.
E5_ENCODER_IDENTITY = {
    "repo": COLQWEN2_MODEL_ID,
    "revision": COLQWEN2_REVISION,
    "weights_sha256": "2f6dbf32fc2db5b045d74ae73b148425d6e03cc1106a047cdcc7e72b6dc53aba",
    "preprocessor_config_sha256": "be69973e9e1f8404b6fb70f246ad8307086d614b31464e3048c387945ac66bf0",
    "tokenizer_sha256": "091aa7594dc2fcfbfa06b9e3c22a5f0562ac14f30375c13af7309407a0e67b8a",
    "torch": "2.15.0",
    "transformers": "5.23.0",
    "dtype": "bfloat16",
    "attn_implementation": "sdpa",
    "batch_size": 1,
    "query_prefix": "Query: ",
    "query_augmentation": "10 x <|endoftext|>",
    "visual_prompt": "<|im_start|>user\n<|vision_start|><|image_pad|><|vision_end|>Describe the image.<|im_end|><|endoftext|>",
    "embedding_rule": "model(**batch).embeddings; rows with attention_mask 0 removed; stored bf16",
}
# notebook 04 (e5-config) asserted these preprocessing values from the pinned preprocessor_config.json.
E5_PREPROCESSOR_SETTINGS = {"min_pixels": 3136, "max_pixels": 602112, "patch_size": 14, "merge_size": 2}


def file_sha256(path: str | Path, chunk: int = 1 << 24) -> str:
    """SHA-256 of a file, read in 16 MB chunks (memory stays flat even for the 4.4 GB weights)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def weights_problem(model_dir: str | Path = DEFAULT_MODEL_DIR, *, expected_bytes: int = COLQWEN2_WEIGHTS_BYTES) -> str | None:
    """Why the checkpoint cannot be loaded, or None. Uses ``os.stat`` only: it never opens the weights.

    On the development machine ``model.safetensors`` is an iCloud "dataless" placeholder;
    reading it would download 4.4 GB onto a nearly full disk, so that is reported instead.
    """
    model_dir = Path(model_dir)
    for name in ("config.json", "preprocessor_config.json", "tokenizer.json", "model.safetensors"):
        if not (model_dir / name).is_file():
            return f"ColQwen2 checkpoint incomplete: {model_dir / name} is missing"
    info = (model_dir / "model.safetensors").stat()
    if getattr(info, "st_flags", 0) & SF_DATALESS:
        return (f"{model_dir / 'model.safetensors'} is an iCloud placeholder (dataless); download the 4.4 GB "
                "checkpoint deliberately before enabling the encoder")
    if info.st_size != expected_bytes:
        return f"ColQwen2 weights have {info.st_size:,} bytes, the E5 spec pins {expected_bytes:,}"
    return None


def check_checkpoint_files(model_dir: str | Path, identity: Mapping[str, Any] = E5_ENCODER_IDENTITY) -> None:
    """The small checkpoint files equal E5's: preprocessor and tokenizer hashes, preprocessing settings."""
    model_dir = Path(model_dir)
    for name, field in (("preprocessor_config.json", "preprocessor_config_sha256"), ("tokenizer.json", "tokenizer_sha256")):
        digest = file_sha256(model_dir / name)
        if digest != identity[field]:
            raise RuntimeError(f"{name} has sha256 {digest[:12]}, E5 used {identity[field][:12]}: a new condition")
    config = json.loads((model_dir / "preprocessor_config.json").read_text())
    settings = {name: config.get(name) for name in E5_PREPROCESSOR_SETTINGS}
    if settings != E5_PREPROCESSOR_SETTINGS:
        raise RuntimeError(f"preprocessing {settings} differs from E5's {E5_PREPROCESSOR_SETTINGS}")


def check_library_versions(torch_version: str, transformers_version: str,
                           identity: Mapping[str, Any] = E5_ENCODER_IDENTITY) -> None:
    """notebook 04's version assertion: transformers exactly, torch up to a local build suffix (e.g. '+cpu')."""
    if transformers_version != identity["transformers"] or not str(torch_version).startswith(identity["torch"]):
        raise RuntimeError(f"torch {torch_version} / transformers {transformers_version} differ from E5's "
                           f"{identity['torch']} / {identity['transformers']}: a new condition")


def check_processor(processor: Any, identity: Mapping[str, Any] = E5_ENCODER_IDENTITY) -> None:
    """notebook 04's processor assertions, plus the query rule observed on a probe text (tokenizer only)."""
    found = {"query_prefix": getattr(processor, "query_prefix", None),
             "query_augmentation": f"10 x {getattr(processor, 'query_augmentation_token', None)}",
             "visual_prompt": getattr(processor, "visual_prompt_prefix", None)}
    expected = {name: identity[name] for name in found}
    if found != expected:
        raise RuntimeError(f"processor settings {found} differ from E5's {expected}")
    token = getattr(processor, "query_augmentation_token")
    ids = processor(text=["probe"], return_tensors="pt")["input_ids"][0]
    text = processor.tokenizer.decode(ids)
    if text != f"{identity['query_prefix']}probe{token * 10}\n":  # the processor's rule: prefix + query + 10 tokens + newline
        raise RuntimeError(f"the processor encodes a query as {text!r}, not E5's 'Query: <question>' + 10 x {token} + newline")


def verified_weights_sha256(model_dir: str | Path, record_path: str | Path, *,
                            expected_sha256: str = E5_ENCODER_IDENTITY["weights_sha256"],
                            expected_bytes: int = COLQWEN2_WEIGHTS_BYTES) -> str:
    """Hash the weights once per file version (size + mtime, as notebook 04 did) and compare with E5's hash.

    Hashing 4.4 GB takes about a minute; the result is kept in ``record_path`` and reused while
    the file's size and modification time are unchanged. Only called after the owner has
    downloaded the weights (``weights_problem`` refuses an iCloud placeholder first).
    """
    model_dir, record_path = Path(model_dir), Path(record_path)
    problem = weights_problem(model_dir, expected_bytes=expected_bytes)
    if problem:
        raise RuntimeError(problem)
    weights = model_dir / "model.safetensors"
    info = weights.stat()
    record = json.loads(record_path.read_text()) if record_path.is_file() else {}
    if record.get("size") != info.st_size or record.get("mtime_ns") != info.st_mtime_ns:
        record = {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "sha256": file_sha256(weights)}
        atomic_write_bytes(record_path, json.dumps(record).encode())
    if record["sha256"] != expected_sha256:
        raise RuntimeError(f"model.safetensors has sha256 {record['sha256'][:12]}, E5 used {expected_sha256[:12]}")
    return record["sha256"]


def _unpadded_pixel_values(torch: Any, batch: Mapping[str, Any]) -> Any:
    """The library's own unpadding (ColQwen2ForRetrieval.forward): keep each image's h * w patch rows."""
    grid = batch["image_grid_thw"]
    offsets = grid[:, 1] * grid[:, 2]
    mask = torch.arange(batch["pixel_values"].shape[1]).unsqueeze(0) < offsets.unsqueeze(1)
    return batch["pixel_values"][mask]


def _synchronize(torch: Any, device: str) -> None:
    if device == "mps":
        torch.mps.synchronize()
    elif device.startswith("cuda"):
        torch.cuda.synchronize()


def _release(torch: Any, device: str) -> None:
    """Free a pass's memory before the next one (notebook 04: gc, then empty the GPU cache)."""
    gc.collect()
    if device == "mps":
        torch.mps.empty_cache()
    elif device.startswith("cuda"):
        torch.cuda.empty_cache()


def _feature_stub(torch: Any) -> Any:
    """A module that stands in for ``model.vlm.visual`` and returns the pass-1 output of the current page."""

    class CachedVisionFeatures(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.features = None

        def forward(self, pixel_values, grid_thw=None, return_dict=True, **kwargs):
            expected = int((grid_thw.prod(-1) // 4).sum())  # one feature per 2 x 2 block of patches
            if self.features is None or self.features.shape[0] != expected:
                raise RuntimeError("cached vision features do not match this page")
            return SimpleNamespace(pooler_output=self.features)

    return CachedVisionFeatures()


class ColQwen2Encoder:
    """ColQwen2 v1.0 page and query encoder, as notebook 04 ran it (bf16, sdpa, batch size 1).

    LIVE PATH, NOT EXECUTED IN TESTS: with real weights it was run only in notebook 04.
    The tests inject a small fake model through ``load_model`` / ``load_processor`` and
    check the orchestration (two passes equal one pass, padding rows removed, temporary
    features consumed); the identity checks are tested on their own.

    Before the first encoding, the real path checks that it is E5's encoder: the hashes of
    the preprocessor and tokenizer files, the preprocessing settings, the torch and
    transformers versions, the processor's prompts and query rule, and (once per weights
    file version) the SHA-256 of the 4.4 GB weights. Any difference raises RuntimeError.

    Pages are encoded in two passes so that the 2.2 B-parameter model never sits whole in
    the 8 GB of memory (E5 spec: 5.5 GB and 35-45 s/page in one pass, ~13 s/page in two):

    - pass 1 keeps only the vision tower ``model.vlm.visual`` and saves each page's
      ``pooler_output`` under ``work_dir``;
    - pass 2 reloads the model, replaces the vision tower by a stub returning those
      features, and calls the library's unmodified forward.

    An interrupted run resumes: pages whose pass-1 features exist skip pass 1. Features are
    kept in a folder named after the model, revision and encoder settings, so features made
    under other settings are never reused.
    """

    def __init__(
        self,
        model_dir: str | Path = DEFAULT_MODEL_DIR,
        *,
        work_dir: str | Path,
        device: str = "mps",
        load_model: Callable[[], Any] | None = None,
        load_processor: Callable[[], Any] | None = None,
    ):
        self.model_dir, self.work_dir, self.device = Path(model_dir), Path(work_dir), device
        self._load_model, self._load_processor = load_model, load_processor
        self.injected = load_model is not None  # tests: a fake model, no checkpoint and no identity checks
        if not self.injected:  # the real checkpoint: refuse early, before any library import or read
            problem = weights_problem(self.model_dir)
            if problem:
                raise RuntimeError(problem)
        settings = {"injected": "fake model (tests)"} if self.injected else dict(E5_ENCODER_IDENTITY)
        settings["device"] = device
        config_hash = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:12]
        self.feature_dir = self.work_dir / f"{COLQWEN2_MODEL_ID.replace('/', '--')}@{COLQWEN2_REVISION[:12]}" / config_hash
        self.identity: dict[str, Any] | None = None
        self._processor = None
        self._query_model = None

    def _libraries(self) -> tuple[Any, Any]:
        """torch and safetensors.torch, imported on first use only (never at application start)."""
        try:
            import torch
            import safetensors.torch as safetensors_torch
        except ImportError as error:  # RuntimeError so that answer_question_b1 falls back to BM25
            raise RuntimeError(f"the ColQwen2 encoder needs torch and safetensors (visualdoc-ai[visual]): {error}") from error
        if self.device == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("device 'mps' is not available; E5 encoded on Apple MPS (another device is a new condition)")
        return torch, safetensors_torch

    def _verify_identity(self, torch: Any) -> None:
        """Run once, before anything is encoded: refuse an encoder that is not E5's (see the class docstring)."""
        if self.identity is not None:
            return
        if self.injected:
            self.identity = {"injected": "fake model (tests)", "device": self.device}
            return
        check_checkpoint_files(self.model_dir)
        try:
            import transformers
        except ImportError as error:
            raise RuntimeError(f"the ColQwen2 encoder needs transformers 5.23.0: {error}") from error
        check_library_versions(torch.__version__, transformers.__version__)
        check_processor(self.processor())
        weights_sha256 = verified_weights_sha256(self.model_dir, self.work_dir / "weights_check.json")
        self.identity = {**E5_ENCODER_IDENTITY, "weights_sha256": weights_sha256, "device": self.device}

    def _model(self) -> Any:
        if self._load_model is not None:
            return self._load_model()
        torch, _ = self._libraries()
        try:
            from transformers import ColQwen2ForRetrieval
        except ImportError as error:
            raise RuntimeError(f"the ColQwen2 encoder needs transformers 5.23.0: {error}") from error
        return ColQwen2ForRetrieval.from_pretrained(self.model_dir, dtype=torch.bfloat16, attn_implementation="sdpa").eval()

    def processor(self) -> Any:
        if self._processor is None:
            if self._load_processor is not None:
                self._processor = self._load_processor()
            else:
                try:
                    from transformers import ColQwen2Processor
                except ImportError as error:
                    raise RuntimeError(f"the ColQwen2 encoder needs transformers 5.23.0: {error}") from error
                self._processor = ColQwen2Processor.from_pretrained(self.model_dir)
        return self._processor

    def describe(self) -> dict[str, Any]:
        """The verified encoder identity, recorded inside each stored index (weights hash included)."""
        if self.identity is None:
            raise RuntimeError("the encoder has not encoded anything yet")
        return {**self.identity, "model_dir": str(self.model_dir), "passes": "2 (vision tower, then language model)"}

    def _encode_with(self, torch: Any, model: Any, batch: Any) -> Any:
        """``model(**batch).embeddings`` for one item, padding rows removed, on the CPU (bf16)."""
        embeddings = model(**batch).embeddings
        _synchronize(torch, self.device)
        keep = batch["attention_mask"][0].bool()
        return embeddings[0][keep].cpu().contiguous()

    @staticmethod
    def _image(png: bytes) -> Any:
        from PIL import Image

        with Image.open(io.BytesIO(png)) as image:
            return image.convert("RGB")

    def encode_pages(self, pngs: Mapping[int, bytes]) -> dict[int, np.ndarray]:
        """{page: float32 (tokens, 128)} for the given page PNGs, by notebook 04's two passes."""
        if not pngs:
            raise ValueError("no page images to encode")
        torch, safetensors_torch = self._libraries()
        self._verify_identity(torch)
        processor = self.processor()
        self.feature_dir.mkdir(parents=True, exist_ok=True)
        for stale in self.feature_dir.glob(".*.tmp"):  # temporaries of an interrupted write
            stale.unlink()
        by_sha = {hashlib.sha256(png).hexdigest(): png for png in pngs.values()}  # identical pages encode once
        feature_path = lambda sha: self.feature_dir / f"{sha}.safetensors"

        # Pass 1: the vision tower alone.
        need_vision = [sha for sha in by_sha if not feature_path(sha).is_file()]
        if need_vision:
            model = self._model()
            visual = model.vlm.visual
            model.vlm.visual = None
            del model
            gc.collect()
            visual.to(self.device)
            with torch.inference_mode():
                for sha in need_vision:
                    batch = processor(images=[self._image(by_sha[sha])], return_tensors="pt")
                    features = visual(_unpadded_pixel_values(torch, batch).to(self.device),
                                      grid_thw=batch["image_grid_thw"].to(self.device), return_dict=True).pooler_output
                    _synchronize(torch, self.device)
                    atomic_write_bytes(feature_path(sha), safetensors_torch.save({"features": features.cpu().contiguous()}))
            del visual
            _release(torch, self.device)

        # Pass 2: the library's unmodified forward, with the vision tower replaced by the pass-1 features.
        model = self._model()
        stub = _feature_stub(torch)
        model.vlm.visual = stub  # the real vision weights are released before the move to the device
        gc.collect()
        model.to(self.device)
        encoded = {}
        with torch.inference_mode():
            for sha, png in by_sha.items():
                batch = processor(images=[self._image(png)], return_tensors="pt").to(self.device)
                stub.features = safetensors_torch.load_file(feature_path(sha))["features"].to(self.device)
                encoded[sha] = self._encode_with(torch, model, batch).float().numpy()  # bf16 -> float32 is exact
        del model, stub
        _release(torch, self.device)
        for sha in by_sha:  # every page is encoded: the temporary features are no longer needed
            feature_path(sha).unlink()
        return {page: encoded[hashlib.sha256(png).hexdigest()] for page, png in pngs.items()}

    def encode_query(self, question: str) -> np.ndarray:
        """float32 (tokens, 128) for one question: 'Query: ' + question + 10 augmentation tokens (the processor's rule)."""
        torch, _ = self._libraries()
        self._verify_identity(torch)
        if self._query_model is None:  # language model only: the vision tower is never needed for text
            model = self._model()
            model.vlm.visual = _feature_stub(torch)
            gc.collect()
            self._query_model = model.to(self.device)
        with torch.inference_mode():
            batch = self.processor()(text=[question], return_tensors="pt").to(self.device)
            return self._encode_with(torch, self._query_model, batch).float().numpy()
