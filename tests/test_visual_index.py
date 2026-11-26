"""Visual index: bf16 safetensors codec, keyed store, E5 import, and the ColQwen2 encoder's orchestration.

The live ColQwen2 encoder is NOT executed here (its 4.4 GB checkpoint is an iCloud
placeholder on the development machine and must never be read by the tests). Its
two-pass orchestration is run on a small fake model instead. The regression tests use
the embeddings notebook 04 cached in E5 and the frozen E5 rankings.
"""

import hashlib
import io
import json
import os
import shutil
from types import SimpleNamespace

import numpy as np
import pytest

import visualdoc.visual_index as visual_index
from conftest import MMLB_DOCUMENTS, MMLB_QUESTIONS, REPO_ROOT
from visualdoc.documents import sha256_file
from visualdoc.retrieval import CachedVisualIndex
from visualdoc.visual_index import (
    DEFAULT_MODEL_DIR,
    E5_ENCODER_IDENTITY,
    E5_PREPROCESSOR_SETTINGS,
    EMBEDDING_DIM,
    RENDER_PROFILE,
    SF_DATALESS,
    ColQwen2Encoder,
    IndexKey,
    IndexKeyMismatch,
    StoreQueryEncoder,
    VisualIndexStore,
    atomic_write_bytes,
    bf16_bits_to_float32,
    check_checkpoint_files,
    check_library_versions,
    check_processor,
    decode_safetensors,
    encode_safetensors,
    float32_to_bf16_bits,
    import_e5_document,
    import_e5_queries,
    query_sha256,
    verified_weights_sha256,
    weights_problem,
)

E5_CACHE = REPO_ROOT / "data" / "cache" / "e5" / "colqwen2-v1.0-hf@ddc07d2317c8" / "af02fac2cb9b"
FROZEN_E5 = REPO_ROOT / "experiments" / "frozen" / "e5" / "tables"
DEV_MANIFEST = REPO_ROOT / "data" / "processed" / "mmlongbench_doc" / "render_manifest_e1.csv"
# Two held-out (E5) documents whose PDFs are fully on disk (not iCloud placeholders); 20 pages each.
PARITY_DOCUMENTS = ["e639029d16094ea71d964e2fb953952b.pdf", "efd88e41c5f2606c57929cac6c1c0605.pdf"]
SHA_A, SHA_B = "a" * 64, "b" * 64


def unit_rows(seed, rows):
    matrix = np.random.default_rng(seed).normal(size=(rows, EMBEDDING_DIM)).astype(np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
    return bf16_bits_to_float32(float32_to_bf16_bits(matrix))  # exactly representable in bf16, like ColQwen2 output


def materialized(path):
    """True when the file exists and its bytes are on disk (reading it will not trigger an iCloud download)."""
    return path.is_file() and not (getattr(path.stat(), "st_flags", 0) & SF_DATALESS)


def require_e5_cache():
    if not (E5_CACHE / "pages").is_dir() or not (E5_CACHE / "queries").is_dir() or not (E5_CACHE / "config.json").exists():
        pytest.skip("E5 embedding cache absent (git-ignored; notebook 04 writes it)")


# --- bfloat16 and the safetensors codec ---------------------------------------------------------------


def test_bf16_rounding_is_round_half_to_even_and_widening_is_exact():
    values = np.array([1.0, 1.00390625, 1.01171875, -2.5e-3, 0.0], dtype=np.float32)
    bits = float32_to_bf16_bits(values)
    # 1 + 2^-8 is halfway between 1.0 and 1.0078125: ties go to the even mantissa (1.0).
    assert bits.tolist() == [0x3F80, 0x3F80, 0x3F82, 0xBB24, 0x0000]
    widened = bf16_bits_to_float32(bits)
    assert np.array_equal(float32_to_bf16_bits(widened), bits)  # bf16 -> f32 -> bf16 loses nothing
    with pytest.raises(ValueError, match="finite"):
        float32_to_bf16_bits(np.array([np.nan], dtype=np.float32))


def test_safetensors_round_trip_keeps_metadata_and_pads_the_header(tmp_path):
    tensors = {"page_0002": unit_rows(2, 3), "page_0001": unit_rows(1, 5)}
    raw = encode_safetensors(tensors, {"model_id": "owner/name", "a": "1"})
    header_length = int.from_bytes(raw[:8], "little")
    assert header_length % 8 == 0
    header = json.loads(raw[8:8 + header_length])
    assert list(header) == ["__metadata__", "page_0001", "page_0002"]  # metadata first, then name order
    decoded, metadata = decode_safetensors(raw)
    assert metadata == {"a": "1", "model_id": "owner/name"}
    assert all(np.array_equal(decoded[name], tensors[name]) for name in tensors)

    # The safetensors library reads the same file (header, names, metadata).
    from safetensors import safe_open

    path = tmp_path / "x.safetensors"
    path.write_bytes(raw)
    with safe_open(str(path), framework="numpy") as handle:
        assert sorted(handle.keys()) == ["page_0001", "page_0002"] and handle.metadata() == metadata


@pytest.mark.parametrize("damage", ["truncated", "bad_dtype", "short_data", "trailing"])
def test_malformed_safetensors_are_refused(damage):
    raw = encode_safetensors({"embedding": unit_rows(0, 2)})
    header_length = int.from_bytes(raw[:8], "little")
    header = json.loads(raw[8:8 + header_length])
    if damage == "truncated":
        raw = raw[:5]
    elif damage == "bad_dtype":
        header["embedding"]["dtype"] = "F16"
        text = json.dumps(header).encode()
        raw = len(text).to_bytes(8, "little") + text + raw[8 + header_length:]
    elif damage == "short_data":
        raw = raw[:-2]
    else:
        raw = raw + b"\0\0"
    with pytest.raises(ValueError):
        decode_safetensors(raw)


def test_codec_rewrites_an_e5_embedding_file_byte_for_byte():
    """Same format as notebook 04's safetensors files: decoding then encoding reproduces them exactly."""
    require_e5_cache()
    files = sorted((E5_CACHE / "pages").glob("*.safetensors"))[:3] + sorted((E5_CACHE / "queries").glob("*.safetensors"))[:2]
    assert files
    for path in files:
        raw = path.read_bytes()
        tensors, metadata = decode_safetensors(raw)
        assert metadata == {} and tensors["embedding"].shape[1] == EMBEDDING_DIM
        assert encode_safetensors(tensors) == raw, path.name


# --- atomic writes, keys and the store ----------------------------------------------------------------


def test_atomic_write_keeps_the_previous_file_when_the_rename_fails(tmp_path, monkeypatch):
    target = tmp_path / "index.safetensors"
    target.write_bytes(b"previous")

    def failing_replace(source, destination):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError, match="disk full"):
        atomic_write_bytes(target, b"new bytes")
    assert target.read_bytes() == b"previous"
    assert [p.name for p in tmp_path.iterdir()] == ["index.safetensors"]  # no temporary left behind


@pytest.mark.parametrize("field, value", [
    ("pdf_sha256", "abc"), ("pdf_sha256", "A" * 64), ("render_profile", "768px"),
    ("model_id", "no-owner"), ("model_revision", "main"),
])
def test_index_key_rejects_ambiguous_parts(field, value):
    with pytest.raises(ValueError):
        IndexKey(**{"pdf_sha256": SHA_A, field: value})


def test_store_round_trip_records_the_key_and_the_page_images(tmp_path):
    store = VisualIndexStore(tmp_path)
    key = IndexKey(SHA_A)
    pages = {1: unit_rows(1, 7), 2: unit_rows(2, 4), 3: unit_rows(3, 9)}
    png_sha = {p: hashlib.sha256(bytes([p])).hexdigest() for p in pages}
    assert store.load(key) is None and not store.has(key)
    path = store.save(key, pages, png_sha256=png_sha, encoder={"device": "test"})
    assert path == tmp_path / "vidore--colqwen2-v1.0-hf@ddc07d2317c8" / RENDER_PROFILE / f"{SHA_A}.safetensors"
    loaded = store.load(key)
    assert sorted(loaded) == [1, 2, 3] and all(np.array_equal(loaded[p], pages[p]) for p in pages)
    assert store.stored_png_sha256(key) == [png_sha[p] for p in (1, 2, 3)]


def test_store_refuses_an_embedding_saved_under_another_key(tmp_path):
    store = VisualIndexStore(tmp_path)
    saved = IndexKey(SHA_A)
    store.save(saved, {1: unit_rows(1, 3)}, png_sha256={1: SHA_B})
    # The same file placed where another PDF's index belongs is detected from the key inside it.
    other = IndexKey(SHA_B)
    store.path(other).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(store.path(saved), store.path(other))
    with pytest.raises(IndexKeyMismatch, match="pdf_sha256"):
        store.load(other)
    # A different render profile or revision is a different key, so nothing is found to reuse.
    assert store.load(IndexKey(SHA_A, render_profile="short512-long1024")) is None
    assert store.load(IndexKey(SHA_A, model_revision="0" * 40)) is None


@pytest.mark.parametrize("pages", [
    {1: np.zeros((3, 64), np.float32)},  # wrong embedding width
    {1: np.zeros((0, EMBEDDING_DIM), np.float32)},  # no token
    {1: np.zeros(EMBEDDING_DIM, np.float32)},  # not a matrix
    {1: np.full((2, EMBEDDING_DIM), np.inf, np.float32)},  # not finite
    {1: unit_rows(1, 2), 3: unit_rows(3, 2)},  # a gap in the page numbers
    {},  # no page
])
def test_store_validates_shapes_and_pages_before_writing(tmp_path, pages):
    store = VisualIndexStore(tmp_path)
    with pytest.raises(ValueError):
        store.save(IndexKey(SHA_A), pages, png_sha256={p: SHA_B for p in pages})
    assert not any(tmp_path.rglob("*.safetensors"))


def test_query_cache_and_query_encoder(tmp_path):
    store = VisualIndexStore(tmp_path)
    question = "How much was spent?"
    encoder = StoreQueryEncoder(store)
    with pytest.raises(RuntimeError, match="live encoder is off"):
        encoder(question)

    class Live:
        calls = 0

        def encode_query(self, text):
            Live.calls += 1
            return unit_rows(len(text), 4)

    live = StoreQueryEncoder(store, Live())
    first = live(question)
    assert np.array_equal(live(question), first) and Live.calls == 1  # second time from the cache
    assert np.array_equal(StoreQueryEncoder(store)(question), first)  # persisted
    # Tampered metadata: a query file under another question's key is refused.
    other = query_sha256("another question")
    shutil.copy(store.query_path(query_sha256(question)), store.query_path(other))
    with pytest.raises(IndexKeyMismatch):
        store.load_query(other)


# --- the live encoder: availability and orchestration on a fake model ---------------------------------


@pytest.fixture
def no_weights_read(monkeypatch):
    """Fail the test if anything opens a file named model.safetensors (builtins.open, io.open or os.open)."""
    import builtins

    def guarded(opener):
        def open_unless_weights(file, *args, **kwargs):
            if str(file).endswith("model.safetensors"):
                raise AssertionError(f"attempted to open the weights: {file}")
            return opener(file, *args, **kwargs)

        return open_unless_weights

    for module, name in ((builtins, "open"), (io, "open"), (os, "open")):
        monkeypatch.setattr(module, name, guarded(getattr(module, name)))


def test_weights_problem_never_reads_the_checkpoint(tmp_path, no_weights_read):
    assert "missing" in weights_problem(tmp_path)
    for name in ("config.json", "preprocessor_config.json", "tokenizer.json"):
        (tmp_path / name).write_text("{}")
    (tmp_path / "placeholder").write_bytes(b"tiny")  # created under another name: the guard blocks opening the weights
    (tmp_path / "placeholder").rename(tmp_path / "model.safetensors")
    assert "bytes" in weights_problem(tmp_path)  # stat only: the guard would fail the test on any open
    with pytest.raises(RuntimeError, match="bytes"):
        ColQwen2Encoder(tmp_path, work_dir=tmp_path / "work")
    with pytest.raises(RuntimeError, match="bytes"):
        verified_weights_sha256(tmp_path, tmp_path / "record.json")
    real = DEFAULT_MODEL_DIR / "model.safetensors"
    if real.is_file() and getattr(real.stat(), "st_flags", 0) & SF_DATALESS:
        # The machine's real checkpoint is an iCloud placeholder: reported from os.stat, never opened.
        assert "dataless" in weights_problem(DEFAULT_MODEL_DIR)
        with pytest.raises(RuntimeError, match="dataless"):
            ColQwen2Encoder(work_dir=tmp_path / "work")
        with pytest.raises(RuntimeError, match="dataless"):
            verified_weights_sha256(DEFAULT_MODEL_DIR, tmp_path / "record.json")


def test_weights_are_hashed_once_per_file_version_and_compared_with_e5(tmp_path, monkeypatch):
    for name in ("config.json", "preprocessor_config.json", "tokenizer.json"):
        (tmp_path / name).write_text("{}")
    (tmp_path / "model.safetensors").write_bytes(b"weights")  # 7 bytes stand in for 4.4 GB
    expected = hashlib.sha256(b"weights").hexdigest()
    hashed, real_hash = [], visual_index.file_sha256
    monkeypatch.setattr(visual_index, "file_sha256", lambda path, *a: hashed.append(path) or real_hash(path))
    record = tmp_path / "work" / "weights_check.json"
    for _ in range(2):
        assert verified_weights_sha256(tmp_path, record, expected_sha256=expected, expected_bytes=7) == expected
    assert len(hashed) == 1 and json.loads(record.read_text())["sha256"] == expected  # hashed once, then reused
    with pytest.raises(RuntimeError, match="E5 used"):
        verified_weights_sha256(tmp_path, record, expected_sha256="0" * 64, expected_bytes=7)


def test_encoder_identity_constants_equal_the_e5_cache_config():
    if not (E5_CACHE / "config.json").exists():
        pytest.skip("E5 embedding cache absent (git-ignored; notebook 04 writes it)")
    config = json.loads((E5_CACHE / "config.json").read_text())
    assert {name: config[name] for name in E5_ENCODER_IDENTITY} == E5_ENCODER_IDENTITY


def test_identity_checks_refuse_a_different_encoder(tmp_path):
    (tmp_path / "preprocessor_config.json").write_text(json.dumps({**E5_PREPROCESSOR_SETTINGS, "max_pixels": 1}))
    (tmp_path / "tokenizer.json").write_text("{}")
    with pytest.raises(RuntimeError, match="preprocessor_config.json has sha256"):
        check_checkpoint_files(tmp_path)  # not E5's files
    same_hashes = {**E5_ENCODER_IDENTITY,
                   "preprocessor_config_sha256": visual_index.file_sha256(tmp_path / "preprocessor_config.json"),
                   "tokenizer_sha256": visual_index.file_sha256(tmp_path / "tokenizer.json")}
    with pytest.raises(RuntimeError, match="preprocessing"):
        check_checkpoint_files(tmp_path, same_hashes)  # right hashes (here), wrong settings

    check_library_versions("2.15.0+cpu", "5.23.0")
    for torch_version, transformers_version in (("2.16.0", "5.23.0"), ("2.15.0", "5.24.0")):
        with pytest.raises(RuntimeError, match="new condition"):
            check_library_versions(torch_version, transformers_version)

    class FakeProcessor:
        def __init__(self, prefix="Query: ", token="<|endoftext|>", repeats=10, prompt=E5_ENCODER_IDENTITY["visual_prompt"]):
            self.query_prefix, self.query_augmentation_token, self.visual_prompt_prefix = prefix, token, prompt
            self.repeats = repeats
            self.tokenizer = SimpleNamespace(decode=lambda ids: ids)

        def __call__(self, text, return_tensors="pt"):
            return {"input_ids": [f"{self.query_prefix}{text[0]}{self.query_augmentation_token * self.repeats}\n"]}

    check_processor(FakeProcessor())
    for wrong in (FakeProcessor(prefix="Q: "), FakeProcessor(repeats=5), FakeProcessor(token="<pad>"),
                  FakeProcessor(prompt="Describe the page.")):
        with pytest.raises(RuntimeError):
            check_processor(wrong)


def test_identity_checks_pass_on_the_real_small_files_and_processor(no_weights_read):
    """The pinned checkpoint's small files, the installed libraries and its processor are E5's (weights never opened)."""
    if not all((DEFAULT_MODEL_DIR / name).is_file() and not getattr((DEFAULT_MODEL_DIR / name).stat(), "st_flags", 0) & SF_DATALESS
               for name in ("preprocessor_config.json", "tokenizer.json", "tokenizer_config.json")):
        pytest.skip("ColQwen2 small checkpoint files absent or iCloud placeholders")
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    check_checkpoint_files(DEFAULT_MODEL_DIR)
    check_library_versions(torch.__version__, transformers.__version__)
    check_processor(transformers.ColQwen2Processor.from_pretrained(DEFAULT_MODEL_DIR))


def fake_colqwen2_parts():
    """A tiny model with ColQwen2ForRetrieval's interface: vlm.visual, padded pixel rows, image-pad tokens."""
    torch = pytest.importorskip("torch")
    from PIL import Image

    image_pad, width = 7, 16

    class Batch(dict):
        def to(self, device):
            return Batch({key: value.to(device) for key, value in self.items()})

    class Processor:
        def __call__(self, images=None, text=None, return_tensors="pt"):
            if images is not None:
                (image,) = images
                pixels = torch.tensor(np.asarray(image.resize((8, 8)), dtype=np.float32) / 255)
                patches = pixels.reshape(4, 2, 4, 2, 3).permute(0, 2, 1, 3, 4).reshape(16, 12)
                padded = torch.zeros(1, 20, 12)
                padded[0, :16] = patches  # 4 padding rows that the model must drop
                ids = [1, 2, *[image_pad] * 4, 3, 0, 0]  # 4 image tokens (16 patches / 2x2 merge), 2 padding
                return Batch(pixel_values=padded.to(torch.bfloat16), image_grid_thw=torch.tensor([[1, 4, 4]]),
                             input_ids=torch.tensor([ids]), attention_mask=torch.tensor([[1] * 7 + [0, 0]]))
            (question,) = text
            ids = [8 + ord(c) % 50 for c in question[:6]] + [0, 0]
            return Batch(input_ids=torch.tensor([ids]), attention_mask=torch.tensor([[1] * (len(ids) - 2) + [0, 0]]))

    class Visual(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.proj = torch.nn.Linear(12, width, dtype=torch.bfloat16)

        def forward(self, pixel_values, grid_thw=None, return_dict=True):
            return SimpleNamespace(pooler_output=self.proj(pixel_values).reshape(-1, 4, width).mean(1))

    class Model(torch.nn.Module):
        def __init__(self):
            torch.manual_seed(0)  # every load gives the same weights, as from_pretrained does
            super().__init__()
            self.vlm = torch.nn.Module()
            self.vlm.visual = Visual()
            self.vlm.embed = torch.nn.Embedding(60, width, dtype=torch.bfloat16)
            self.head = torch.nn.Linear(width, EMBEDDING_DIM, dtype=torch.bfloat16)

        def forward(self, input_ids, attention_mask, pixel_values=None, image_grid_thw=None):
            hidden = self.vlm.embed(input_ids)
            if pixel_values is not None:
                offsets = image_grid_thw[:, 1] * image_grid_thw[:, 2]  # the library unpads inside its forward
                mask = torch.arange(pixel_values.shape[1]).unsqueeze(0) < offsets.unsqueeze(1)
                features = self.vlm.visual(pixel_values[mask], grid_thw=image_grid_thw, return_dict=True).pooler_output
                hidden = hidden.clone()
                hidden[input_ids == image_pad] = features
            out = torch.nn.functional.normalize(self.head(hidden), dim=-1)
            return SimpleNamespace(embeddings=out * attention_mask.unsqueeze(-1))

    def png(seed):
        rgb = (np.random.default_rng(seed).random((40, 30, 3)) * 255).astype(np.uint8)
        buffer = io.BytesIO()
        Image.fromarray(rgb).save(buffer, format="PNG")
        return buffer.getvalue(), Image.fromarray(rgb)

    return torch, Model, Processor, png


def test_fake_two_pass_encoding_equals_the_single_pass_forward(tmp_path):
    """Orchestration check on a FAKE model (the real ColQwen2 path is not executed in tests)."""
    torch, Model, Processor, png = fake_colqwen2_parts()
    loads = []
    encoder = ColQwen2Encoder(work_dir=tmp_path / "work", device="cpu",
                              load_model=lambda: loads.append(1) or Model(), load_processor=Processor)
    (png1, image1), (png2, _) = png(1), png(2)
    encoded = encoder.encode_pages({1: png1, 2: png2, 3: png1})  # page 3 repeats page 1: encoded once
    assert len(loads) == 2  # pass 1 (vision tower), pass 2 (language model)
    assert not list(encoder.feature_dir.iterdir())  # pass-1 features consumed
    # Features are kept per model, revision and settings: another device never reuses them.
    assert encoder.feature_dir.parent == tmp_path / "work" / "vidore--colqwen2-v1.0-hf@ddc07d2317c8"
    other = ColQwen2Encoder(work_dir=tmp_path / "work", device="mps", load_model=Model, load_processor=Processor)
    assert other.feature_dir != encoder.feature_dir
    assert encoder.describe()["injected"] == "fake model (tests)"

    single = Model()
    batch = Processor()(images=[image1.convert("RGB")], return_tensors="pt")
    with torch.inference_mode():
        reference = single(**batch).embeddings[0][batch["attention_mask"][0].bool()]
    assert encoded[1].shape == (7, EMBEDDING_DIM)  # the two padding rows are removed
    assert torch.equal(torch.from_numpy(encoded[1]), reference.float())  # bitwise, as E5 required
    assert np.array_equal(encoded[3], encoded[1]) and not np.array_equal(encoded[2], encoded[1])

    query = encoder.encode_query("How much?")
    qbatch = Processor()(text=["How much?"], return_tensors="pt")
    with torch.inference_mode():
        expected = single(**qbatch).embeddings[0][qbatch["attention_mask"][0].bool()]
    assert torch.equal(torch.from_numpy(query), expected.float())


def test_fake_encoding_resumes_after_an_interrupted_second_pass(tmp_path):
    _, Model, Processor, png = fake_colqwen2_parts()
    loads = []

    def load_then_fail():
        loads.append(1)
        if len(loads) == 2:
            raise RuntimeError("interrupted")
        return Model()

    work = tmp_path / "work"
    pages = {1: png(1)[0], 2: png(2)[0]}
    first = ColQwen2Encoder(work_dir=work, device="cpu", load_model=load_then_fail, load_processor=Processor)
    with pytest.raises(RuntimeError, match="interrupted"):
        first.encode_pages(pages)
    assert len(list(first.feature_dir.glob("*.safetensors"))) == 2  # pass-1 features survived the interruption
    loads.clear()
    resumed = ColQwen2Encoder(work_dir=work, device="cpu", load_model=lambda: loads.append(1) or Model(),
                              load_processor=Processor).encode_pages(pages)
    assert len(loads) == 1 and sorted(resumed) == [1, 2]  # pass 1 skipped


# --- regression: the frozen E5 visual rankings ---------------------------------------------------------


def frozen_visual_rankings():
    pd = pytest.importorskip("pandas")
    rankings = pd.read_parquet(FROZEN_E5 / "rankings.parquet")
    return rankings[rankings["arm"] == "V"]


def development_questions(qids):
    """Question text of development question ids only (the frame's other rows are never used or printed)."""
    pd = pytest.importorskip("pandas")
    if not MMLB_QUESTIONS.is_file():
        pytest.skip("MMLongBench-Doc question table absent (notebook 00 downloads it)")
    table = pd.read_parquet(MMLB_QUESTIONS, columns=["doc_id", "question"])
    return {qid: table.iloc[int(qid.removeprefix("mmlb-"))] for qid in qids}


def test_cached_e5_embeddings_reproduce_every_frozen_visual_ranking():
    """retrieval.CachedVisualIndex over this module's decoding of the E5 cache = frozen arm V (175 questions)."""
    require_e5_cache()
    pd = pytest.importorskip("pandas")
    frozen = frozen_visual_rankings()
    columns = ["doc_id", "page", "sha256"]
    manifest = pd.read_csv(FROZEN_E5 / "render_manifest_heldout.csv")[columns]
    if not DEV_MANIFEST.is_file():  # git-ignored (notebook 00): without it the 57 development questions cannot be checked
        pytest.skip(f"{DEV_MANIFEST.name} absent: run notebook 00; this test checks all 175 questions or none")
    manifest = pd.concat([manifest, pd.read_csv(DEV_MANIFEST)[columns]], ignore_index=True)
    questions = development_questions(frozen["qid"])
    page_sha = manifest.set_index(["doc_id", "page"])["sha256"]
    load = lambda path: decode_safetensors(path.read_bytes())[0]["embedding"]
    checked, worst = 0, 0.0
    for doc_id, group in frozen.groupby("doc_id"):
        pages = sorted(manifest.loc[manifest["doc_id"] == doc_id, "page"])
        embeddings = {p: load(E5_CACHE / "pages" / f"{page_sha[(doc_id, p)]}.safetensors") for p in pages}
        for row in group.itertuples():
            question = questions[row.qid]
            assert question["doc_id"] == doc_id
            query = load(E5_CACHE / "queries" / f"{query_sha256(question['question'])}.safetensors")
            ranking = CachedVisualIndex(embeddings, lambda _: query).rank("question text not needed here")
            assert [p for p, _ in ranking] == list(row.pages), row.qid
            worst = max(worst, float(np.abs(np.array([s for _, s in ranking]) - np.asarray(row.scores)).max()))
            checked += 1
    assert checked == len(frozen) == 175 and worst < 1e-5, (checked, worst)


@pytest.mark.parametrize("doc_id", PARITY_DOCUMENTS)
def test_store_imported_from_the_pdf_reproduces_frozen_rankings(tmp_path, doc_id):
    """PDF -> render -> PNG SHA-256 -> E5 embedding -> store (keyed by the PDF) -> reload -> MaxSim = frozen V."""
    require_e5_cache()
    pdf = MMLB_DOCUMENTS / doc_id
    if not materialized(pdf):
        pytest.skip(f"{doc_id} absent or an iCloud placeholder")
    pd = pytest.importorskip("pandas")
    store = VisualIndexStore(tmp_path)
    key = import_e5_document(pdf, E5_CACHE, store)
    assert import_e5_queries(E5_CACHE, store) == len(list((E5_CACHE / "queries").glob("*.safetensors")))
    assert key == IndexKey(sha256_file(pdf))

    manifest = pd.read_csv(FROZEN_E5 / "render_manifest_heldout.csv")
    expected_sha = manifest[manifest["doc_id"] == doc_id].sort_values("page")["sha256"].tolist()
    assert store.stored_png_sha256(key) == expected_sha  # today's renders are E5's page images

    fresh = VisualIndexStore(tmp_path)  # a new instance: everything comes from disk
    index = CachedVisualIndex(fresh.load(key), StoreQueryEncoder(fresh))
    frozen = frozen_visual_rankings()
    frozen = frozen[frozen["doc_id"] == doc_id]
    questions = development_questions(frozen["qid"])
    assert len(frozen) == 7
    for row in frozen.itertuples():
        ranking = index.rank(questions[row.qid]["question"])
        assert [p for p, _ in ranking] == list(row.pages), row.qid
        assert np.allclose([s for _, s in ranking], row.scores, rtol=0, atol=1e-5), row.qid


def test_import_refuses_a_pdf_the_e5_cache_never_encoded(tmp_path):
    require_e5_cache()
    import pymupdf

    pdf = tmp_path / "new.pdf"
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "A page E5 never saw.")
    document.save(pdf)
    with pytest.raises(FileNotFoundError, match="1 of 1 pages"):
        import_e5_document(pdf, E5_CACHE, VisualIndexStore(tmp_path / "store"))
    assert not any((tmp_path / "store").rglob("*.safetensors"))


# --- archived page images (renders that differ by processor) --------------------------------------------


def archived_page_fixture(tmp_path, *, png=None, pdf_sha=None, tamper_manifest=False):
    """A one-page PDF, a frozen-style package (manifest + SHA256SUMS), an archived PNG and its record, under tmp_path."""
    import pymupdf
    from visualdoc.documents import render_pages

    pdf = tmp_path / "doc.pdf"
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "One page.")
    document.save(pdf)
    rendered = render_pages(pdf, [1])
    archived = rendered[1] if png is None else png  # stands in for the M1's image
    image = tmp_path / "images" / "page_001.png"
    image.parent.mkdir()
    image.write_bytes(archived)
    sha = hashlib.sha256(archived).hexdigest()
    (tmp_path / "pkg" / "tables").mkdir(parents=True)
    manifest = tmp_path / "pkg" / "tables" / "render_manifest.csv"
    manifest.write_text(f"doc_id,page,width_px,height_px,sha256,image_path\ndoc.pdf,1,0,0,{sha},images/page_001.png\n")
    (tmp_path / "pkg" / "SHA256SUMS").write_text(f"{hashlib.sha256(manifest.read_bytes()).hexdigest()}  tables/render_manifest.csv\n")
    if tamper_manifest:
        manifest.write_text(manifest.read_text() + "\n")
    records = tmp_path / "records.json"
    records.write_text(json.dumps({"pages": [{"doc_id": "doc.pdf", "page": 1, "pdf_sha256": pdf_sha or sha256_file(pdf),
                                              "archived_png_sha256": sha, "image_path": "images/page_001.png",
                                              "frozen_manifest": "pkg/tables/render_manifest.csv"}]}))
    return pdf, rendered, records, sha


def test_archived_page_is_accepted_only_with_its_full_provenance(tmp_path):
    pdf, rendered, records, sha = archived_page_fixture(tmp_path)
    accepted = visual_index.verified_archived_pages(pdf, [1], rendered, records_file=records, root=tmp_path)
    assert accepted == {1: {"png_sha256": sha, "image_path": "images/page_001.png",
                            "rendered_png_sha256": hashlib.sha256(rendered[1]).hexdigest()}}
    assert visual_index.verified_archived_pages(pdf, [2], rendered, records_file=records, root=tmp_path) == {}  # not listed
    assert visual_index.verified_archived_pages(pdf, [1], rendered, records_file=tmp_path / "none.json", root=tmp_path) == {}


@pytest.mark.parametrize("problem", ["pdf", "image", "manifest", "size"])
def test_archived_page_with_broken_provenance_is_refused(tmp_path, problem):
    from PIL import Image

    options = {"pdf": {"pdf_sha": "0" * 64}, "manifest": {"tamper_manifest": True}}.get(problem, {})
    if problem == "size":
        buffer = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buffer, format="PNG")
        options = {"png": buffer.getvalue()}
    pdf, rendered, records, _ = archived_page_fixture(tmp_path, **options)
    if problem == "image":
        image = tmp_path / "images" / "page_001.png"
        image.write_bytes(image.read_bytes() + b"\0")
    with pytest.raises(IndexKeyMismatch):
        visual_index.verified_archived_pages(pdf, [1], rendered, records_file=records, root=tmp_path)


def test_e639_page_15_is_imported_from_its_archived_m1_image_and_recorded(tmp_path):
    """The one recorded substitution: page 15's M1 image (frozen hash) and its E5 embedding, provenance kept in the store."""
    require_e5_cache()
    pdf = MMLB_DOCUMENTS / PARITY_DOCUMENTS[0]
    if not materialized(pdf):
        pytest.skip(f"{pdf.name} absent or an iCloud placeholder")
    store = VisualIndexStore(tmp_path)
    key = import_e5_document(pdf, E5_CACHE, store)
    _, metadata = decode_safetensors(store.path(key).read_bytes())
    archived = json.loads(metadata["encoder"]).get("archived_page_images", {})
    assert set(archived) <= {"15"}  # empty where the render already equals the M1's (on the M1 itself)
    if archived:
        assert archived["15"]["png_sha256"] == "31c14c7d8006b404b9ab461bc7b9efb4d20800e0b926493b5be9c027ebb70f7a"
        assert archived["15"]["rendered_png_sha256"] != archived["15"]["png_sha256"]
