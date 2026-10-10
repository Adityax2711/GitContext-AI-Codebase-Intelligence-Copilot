"""Tests for citation extraction, validation, and source mapping."""

import pytest
from gitcontext.citations import (
    extract_citation_indices,
    format_sources_list,
    remove_or_flag_invalid_citations,
    verify_citations,
)
from gitcontext.models import CodeChunk, SearchResult


@pytest.fixture
def sample_chunks():
    chunk1 = CodeChunk.create(
        repository="demo_repo",
        source_type="code",
        file_path="src/auth.py",
        symbol_or_heading="class UserSessionManager",
        programming_language="python",
        start_line=22,
        end_line=38,
        content="class UserSessionManager:\n    def __init__(self, expiry=3600): ...",
    )
    chunk2 = CodeChunk.create(
        repository="demo_repo",
        source_type="code",
        file_path="src/payment.py",
        symbol_or_heading="def calculate_tax",
        programming_language="python",
        start_line=16,
        end_line=19,
        content="def calculate_tax(amount, rate=0.08): return int(amount * rate)",
    )
    return [chunk1, chunk2]


def test_extract_bracket_citation_indices():
    text = "User sessions expire after one hour [1]. Taxes are 8% [2]. Both combined [1, 2]."
    indices = extract_citation_indices(text)
    assert indices == [1, 2, 1, 2]


def test_verify_valid_citations(sample_chunks):
    answer = (
        "Facts:\n"
        "- Session expiry is configured in UserSessionManager [1].\n"
        "- Sales tax is computed with an 8% default rate [2].\n"
        "Inferences:\n- None."
    )
    result = verify_citations(answer=answer, evidence=sample_chunks)

    assert not result.has_invalid_citations
    assert len(result.valid_citations) == 2
    assert len(result.sources) == 2

    s1 = result.sources[0]
    assert s1.source_index == 1
    assert s1.file_path == "src/auth.py"
    assert s1.start_line == 22
    assert s1.end_line == 38
    assert s1.symbol_or_heading == "class UserSessionManager"

    s2 = result.sources[1]
    assert s2.source_index == 2
    assert s2.file_path == "src/payment.py"
    assert s2.start_line == 16
    assert s2.end_line == 19


def test_verify_invented_citations(sample_chunks):
    # Model cites chunk [1], but hallucinates non-existent chunks [3] and [99]
    answer = (
        "Facts:\n"
        "- Session expiry is 3600s [1].\n"
        "- Database is Postgres [3].\n"
        "- Redis is used for caching [99].\n"
        "Inferences:\n- None."
    )
    result = verify_citations(answer=answer, evidence=sample_chunks, strip_invalid=True)

    assert result.has_invalid_citations
    assert 3 in result.invalid_citations
    assert 99 in result.invalid_citations
    assert len(result.valid_citations) == 1
    assert result.valid_citations[0].source_index == 1

    # Check that invalid citations are stripped in cleaned_answer
    assert "[3]" not in result.cleaned_answer
    assert "[99]" not in result.cleaned_answer
    assert "[1]" in result.cleaned_answer


def test_verify_invalid_chunk_line_ranges():
    # Chunk with invalid line range: start_line > end_line
    bad_chunk = CodeChunk(
        chunk_id="bad1",
        repository="demo",
        source_type="code",
        file_path="corrupt.py",
        symbol_or_heading="broken",
        programming_language="python",
        start_line=100,
        end_line=50,  # Invalid
        content="pass",
        content_hash="abc",
    )
    answer = "This references broken code [1]."
    result = verify_citations(answer=answer, evidence=[bad_chunk])

    assert 1 in result.invalid_citations
    assert len(result.valid_citations) == 0


def test_format_sources_list(sample_chunks):
    result = verify_citations(
        answer="Token expiry [1] and tax [2].",
        evidence=sample_chunks,
    )
    formatted = format_sources_list(result.sources)
    assert "[1] src/auth.py:L22-L38 (class UserSessionManager)" in formatted
    assert "[2] src/payment.py:L16-L19 (def calculate_tax)" in formatted


def test_format_sources_list_empty():
    assert "(No citations found)" in format_sources_list([])
