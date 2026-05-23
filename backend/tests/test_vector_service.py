import pytest

from app.services.vector_service import RetrievedChunk, VectorService


class _FakeVectors(list):
    def tolist(self):
        return list(self)


class FakeEmbedder:
    def encode(self, texts, normalize_embeddings=True):
        return _FakeVectors([[float(len(text) % 7)] for text in texts])


class FakeCollection:
    def __init__(self):
        self.deleted_where = []
        self.upsert_payload = None
        self.query_kwargs = None

    def delete(self, where):
        self.deleted_where.append(where)

    def upsert(self, ids, documents, metadatas, embeddings):
        self.upsert_payload = {
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
            "embeddings": embeddings,
        }

    def query(self, **kwargs):
        self.query_kwargs = kwargs
        return {
            "documents": [["chunk A", "chunk B"]],
            "metadatas": [[
                {"article_id": "a1", "title": "Article 1", "category_id": "c1", "chunk_index": 0},
                {"article_id": "a2", "title": "Article 2", "category_id": "c2", "chunk_index": 1},
            ]],
            "distances": [[0.15, 0.65]],
        }


class BrokenCollection:
    def query(self, **kwargs):
        raise RuntimeError("broken index")


@pytest.fixture(autouse=True)
def reset_vector_state():
    VectorService.reset_cache()


def test_chunk_text_returns_multiple_chunks(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "VECTOR_CHUNK_SIZE", 120)
    monkeypatch.setattr(settings, "VECTOR_CHUNK_OVERLAP", 20)

    chunks = VectorService._chunk_text("x" * 360)
    assert len(chunks) >= 3


def test_upsert_article_writes_chunks(monkeypatch: pytest.MonkeyPatch):
    fake_collection = FakeCollection()
    monkeypatch.setattr(VectorService, "_ensure_ready", classmethod(lambda cls: True))
    monkeypatch.setattr(VectorService, "_embedder", FakeEmbedder())
    monkeypatch.setattr(VectorService, "_collection", fake_collection)

    VectorService.upsert_article(
        article_id="article-1",
        title="Ring care",
        text_content="A" * 1200,
        category_id="cat-1",
    )

    assert fake_collection.deleted_where == [{"article_id": "article-1"}]
    assert fake_collection.upsert_payload is not None
    assert len(fake_collection.upsert_payload["ids"]) >= 2
    assert fake_collection.upsert_payload["metadatas"][0]["article_id"] == "article-1"


def test_search_parses_result_and_scores(monkeypatch: pytest.MonkeyPatch):
    fake_collection = FakeCollection()
    monkeypatch.setattr(VectorService, "_ensure_ready", classmethod(lambda cls: True))
    monkeypatch.setattr(VectorService, "_embedder", FakeEmbedder())
    monkeypatch.setattr(VectorService, "_collection", fake_collection)

    chunks = VectorService.search(query="how to clean ring", top_k=3, category_id="c1")

    assert len(chunks) == 2
    assert isinstance(chunks[0], RetrievedChunk)
    assert chunks[0].article_id == "a1"
    assert chunks[0].score == pytest.approx(0.85, rel=1e-3)
    assert fake_collection.query_kwargs["where"] == {"category_id": "c1"}


def test_search_returns_empty_when_not_ready(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(VectorService, "_ensure_ready", classmethod(lambda cls: False))
    assert VectorService.search(query="test") == []


def test_search_returns_empty_when_query_still_fails_after_reconnect(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(VectorService, "_ensure_ready", classmethod(lambda cls: True))
    monkeypatch.setattr(VectorService, "_embedder", FakeEmbedder())
    monkeypatch.setattr(VectorService, "_collection", BrokenCollection())

    def fake_reconnect(cls):
        cls._collection = BrokenCollection()
        return True

    monkeypatch.setattr(VectorService, "_reconnect_collection", classmethod(fake_reconnect))

    assert VectorService.search(query="test") == []
