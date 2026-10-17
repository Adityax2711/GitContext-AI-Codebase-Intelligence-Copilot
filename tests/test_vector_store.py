"""Unit tests for QdrantVectorStore and Hybrid Retrieval."""

from pathlib import Path
from gitcontext.models import CodeChunk
from gitcontext.retrieval import HybridRetriever
from gitcontext.vector_store import QdrantVectorStore, compute_deterministic_embedding


def test_deterministic_embedding():
    emb1 = compute_deterministic_embedding("def process_payment(amount: float):")
    emb2 = compute_deterministic_embedding("def process_payment(amount: float):")
    emb3 = compute_deterministic_embedding("def authenticate_user(token: str):")

    assert len(emb1) == 384
    assert emb1 == emb2
    assert emb1 != emb3


def test_qdrant_vector_store_in_memory():
    store = QdrantVectorStore(in_memory=True)
    if not store.is_available():
        return

    chunk1 = CodeChunk.create(
        repository="ecommerce",
        source_type="code",
        file_path="src/billing.py",
        symbol_or_heading="def charge_customer",
        programming_language="python",
        start_line=10,
        end_line=20,
        content="def charge_customer(card_id: str, amount: int):\n    return gateway.charge(card_id, amount)\n",
    )
    chunk2 = CodeChunk.create(
        repository="ecommerce",
        source_type="code",
        file_path="src/auth.py",
        symbol_or_heading="def verify_jwt_token",
        programming_language="python",
        start_line=1,
        end_line=15,
        content="def verify_jwt_token(token: str):\n    return jwt.decode(token, secret_key)\n",
    )

    count = store.index_chunks([chunk1, chunk2])
    assert count == 2

    # Query for billing
    results = store.search("charge credit card customer", chunks=[chunk1, chunk2], top_k=1)
    assert len(results) == 1
    assert results[0].chunk.symbol_or_heading == "def charge_customer"
    assert results[0].rank == 1


def test_hybrid_retriever_with_qdrant():
    store = QdrantVectorStore(in_memory=True)
    if not store.is_available():
        return

    chunk1 = CodeChunk.create(
        repository="ecommerce",
        source_type="code",
        file_path="src/billing.py",
        symbol_or_heading="def charge_customer",
        programming_language="python",
        start_line=10,
        end_line=20,
        content="def charge_customer(card_id: str, amount: int):\n    return gateway.charge(card_id, amount)\n",
    )
    chunk2 = CodeChunk.create(
        repository="ecommerce",
        source_type="code",
        file_path="src/auth.py",
        symbol_or_heading="def verify_jwt_token",
        programming_language="python",
        start_line=1,
        end_line=15,
        content="def verify_jwt_token(token: str):\n    return jwt.decode(token, secret_key)\n",
    )

    store.index_chunks([chunk1, chunk2])

    hybrid = HybridRetriever(chunks=[chunk1, chunk2], vector_store=store)
    results = hybrid.search("charge customer", top_k=2)

    assert len(results) == 2
    assert results[0].chunk.symbol_or_heading == "def charge_customer"
    assert results[0].score > 0


def test_qdrant_disk_persistence(tmp_path: Path):
    qdrant_dir = tmp_path / "qdrant_data"
    store = QdrantVectorStore(storage_path=qdrant_dir, in_memory=False)
    if not store.is_available():
        return

    chunk = CodeChunk.create(
        repository="test_repo",
        source_type="code",
        file_path="test.py",
        symbol_or_heading="def sample",
        programming_language="python",
        start_line=1,
        end_line=5,
        content="def sample(): pass\n",
    )

    indexed = store.index_chunks([chunk])
    assert indexed == 1
    assert qdrant_dir.exists()
