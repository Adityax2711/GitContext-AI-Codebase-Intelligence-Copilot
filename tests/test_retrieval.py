"""Unit tests for BM25 retrieval and code-aware tokenization."""

from gitcontext.models import CodeChunk
from gitcontext.retrieval import (
    BM25Retriever,
    search_index,
    tokenize_code_and_text,
)


def test_tokenize_camel_and_snake_case():
    text = "getUserById process_order_data XMLParser"
    tokens = tokenize_code_and_text(text)

    assert "getuserbyid" in tokens
    assert "get" in tokens
    assert "user" in tokens
    assert "by" in tokens
    assert "id" in tokens
    assert "process" in tokens
    assert "order" in tokens
    assert "data" in tokens


def test_bm25_retrieval_ranking():
    chunks = [
        CodeChunk.create(
            repository="demo",
            source_type="code",
            file_path="src/payment.py",
            symbol_or_heading="def process_stripe_payment",
            programming_language="python",
            start_line=10,
            end_line=25,
            content="def process_stripe_payment(amount: float, card_token: str):\n    # Process credit card charges via Stripe API\n    return stripe.Charge.create(amount=amount, card=card_token)\n",
        ),
        CodeChunk.create(
            repository="demo",
            source_type="code",
            file_path="src/auth.py",
            symbol_or_heading="def login_user",
            programming_language="python",
            start_line=1,
            end_line=15,
            content="def login_user(username, password):\n    # Authenticate user with hashed password\n    return verify_password(username, password)\n",
        ),
        CodeChunk.create(
            repository="demo",
            source_type="documentation",
            file_path="README.md",
            symbol_or_heading="GitContext > Payment Gateway Integration",
            programming_language="markdown",
            start_line=1,
            end_line=10,
            content="## Payment Gateway Integration\nWe support Stripe payments for recurring subscriptions.\n",
        ),
    ]

    retriever = BM25Retriever(chunks)

    # Test payment search
    results = retriever.search("How are Stripe payments handled?", top_k=2)
    assert len(results) == 2
    symbols = [r.chunk.symbol_or_heading for r in results]
    assert "def process_stripe_payment" in symbols or "GitContext > Payment Gateway Integration" in symbols
    assert results[0].score > 0

    # Test login search
    auth_results = retriever.search("user password authentication", top_k=1)
    assert len(auth_results) == 1
    assert auth_results[0].chunk.symbol_or_heading == "def login_user"


def test_search_empty_index():
    assert search_index("any query", chunks=[]) == []
