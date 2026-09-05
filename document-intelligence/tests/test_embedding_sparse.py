"""Tests for the pure half of sparse encoding (ADR-0054).

None of these load a model. Everything that decides what reaches the index —
windowing, pooling, feature sanitisation — is a pure function precisely so that
it is covered by tests that run in CI on a machine with no GPU and no 2.3GB
download.
"""

from __future__ import annotations

import pytest

from document_intelligence.embeddings.sparse import (
    DEFAULT_MIN_WEIGHT,
    SparseEncoder,
    chunk_text,
    iter_batches,
    pool_sparse_chunks,
    sanitize_features,
)


class TestChunkText:
    def test_short_text_is_one_chunk(self) -> None:
        assert chunk_text("Art. 1 Der Hund", chunk_chars=100, overlap=20) == ["Art. 1 Der Hund"]

    def test_shrinking_chunk_chars_below_the_default_overlap_raises(self) -> None:
        """A caller who narrows the window without narrowing the overlap gets an
        error, not a silently different chunking."""
        with pytest.raises(ValueError):
            chunk_text("text", chunk_chars=100)

    def test_empty_and_whitespace_produce_no_chunks(self) -> None:
        assert chunk_text("") == []
        assert chunk_text("   \n\t ") == []

    def test_long_text_is_windowed_with_overlap(self) -> None:
        text = "a" * 250
        chunks = chunk_text(text, chunk_chars=100, overlap=20)
        assert len(chunks) > 1
        assert all(len(c) <= 100 for c in chunks)

    def test_every_character_survives_windowing(self) -> None:
        """The failure this guards is silent truncation, so assert coverage."""
        text = "".join(chr(ord("a") + i % 26) for i in range(1000))
        chunks = chunk_text(text, chunk_chars=100, overlap=20)
        rebuilt = set()
        step = 80
        for index, chunk in enumerate(chunks):
            start = index * step
            rebuilt.update(range(start, start + len(chunk)))
        assert rebuilt.issuperset(range(len(text)))

    def test_trailing_window_adding_nothing_new_is_dropped(self) -> None:
        """175 chars at chunk=100/step=80 gives windows 0-100, 80-175 and a third
        start at 160 whose 15 characters window 80 already covers."""
        chunks = chunk_text("x" * 175, chunk_chars=100, overlap=20)
        assert len(chunks) == 2

    def test_a_trailing_window_that_does_add_characters_is_kept(self) -> None:
        chunks = chunk_text("x" * 185, chunk_chars=100, overlap=20)
        assert len(chunks) == 3

    @pytest.mark.parametrize(
        ("chunk_chars", "overlap"),
        [(0, 0), (-1, 0), (100, 100), (100, 200), (100, -1)],
    )
    def test_invalid_windows_are_rejected(self, chunk_chars: int, overlap: int) -> None:
        with pytest.raises(ValueError):
            chunk_text("text", chunk_chars=chunk_chars, overlap=overlap)


class TestPooling:
    def test_max_pooling_takes_the_strongest_expression(self) -> None:
        pooled = pool_sparse_chunks([{"t1": 0.2, "t2": 0.9}, {"t1": 0.7, "t3": 0.1}])
        assert pooled == {"t1": 0.7, "t2": 0.9, "t3": 0.1}

    def test_pooling_is_not_summation(self) -> None:
        """Sum would make weight a proxy for document length — see the docstring."""
        pooled = pool_sparse_chunks([{"t1": 0.5}] * 10)
        assert pooled["t1"] == 0.5

    def test_no_chunks_pools_to_empty(self) -> None:
        assert pool_sparse_chunks([]) == {}


class TestSanitizeFeatures:
    def test_integer_token_ids_become_prefixed_string_keys(self) -> None:
        assert sanitize_features({42: 0.5}) == {"t42": 0.5}

    def test_already_prefixed_keys_are_kept(self) -> None:
        assert sanitize_features({"t42": 0.5}) == {"t42": 0.5}

    def test_zero_and_negative_weights_are_dropped(self) -> None:
        """`rank_features` rejects the whole document on a non-positive value."""
        assert sanitize_features({1: 0.0, 2: -0.3, 3: 0.5}) == {"t3": 0.5}

    def test_weights_below_the_floor_are_dropped(self) -> None:
        cleaned = sanitize_features({1: DEFAULT_MIN_WEIGHT / 2, 2: DEFAULT_MIN_WEIGHT})
        assert cleaned == {"t2": DEFAULT_MIN_WEIGHT}

    def test_a_key_containing_a_dot_is_refused(self) -> None:
        """A `.` is read as object nesting by OpenSearch — the defect this avoids."""
        assert sanitize_features({"t1.5": 0.9}) == {}

    def test_a_decoded_token_string_is_refused_rather_than_mangled(self) -> None:
        assert sanitize_features({"Hund": 0.9}) == {}

    def test_non_numeric_weights_are_skipped_not_raised(self) -> None:
        assert sanitize_features({1: "heavy", 2: 0.5}) == {"t2": 0.5}


class _FakeModel:
    """Records what it was asked to encode; returns one feature per chunk."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, sentences, **kwargs):
        self.calls.append(list(sentences))
        return {"lexical_weights": [{index + 1: 0.5} for index, _ in enumerate(sentences)]}


class TestSparseEncoder:
    def test_documents_are_chunked_pooled_and_returned_in_order(self) -> None:
        model = _FakeModel()
        encoder = SparseEncoder(_model=model, chunk_chars=100, chunk_overlap=20)

        vectors = encoder.encode_documents(["short text", "y" * 500])

        assert len(vectors) == 2
        # Both documents' chunks go to the model in ONE flat batch, so a corpus
        # mixing a constitution with a two-page ordinance keeps the GPU busy.
        assert len(model.calls) == 1
        assert len(model.calls[0]) > 2

    def test_an_empty_document_yields_an_empty_vector_not_a_crash(self) -> None:
        encoder = SparseEncoder(_model=_FakeModel())
        assert encoder.encode_documents(["", "   "]) == [{}, {}]

    def test_all_empty_input_never_calls_the_model(self) -> None:
        model = _FakeModel()
        SparseEncoder(_model=model).encode_documents(["", ""])
        assert model.calls == []

    def test_query_encoding_uses_the_same_path_as_documents(self) -> None:
        model = _FakeModel()
        encoder = SparseEncoder(_model=model)
        vector = encoder.encode_query("darf ich meinen Hund mitnehmen")
        assert vector == {"t1": 0.5}
        assert model.calls == [["darf ich meinen Hund mitnehmen"]]


class TestIterBatches:
    def test_batches_cover_every_item(self) -> None:
        assert list(iter_batches([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]

    def test_zero_batch_size_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            list(iter_batches([1], 0))
