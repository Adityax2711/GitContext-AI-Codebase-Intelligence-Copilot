"""Tests for codebase assistant orchestration and edge cases with mocked LLM."""

from pathlib import Path
from unittest.mock import patch
import pytest

from gitcontext.assistant import ask_codebase
from gitcontext.cli import main
from gitcontext.llm import LLMError, MissingAPIKeyError, MockLLMClient, get_llm_client
from gitcontext.models import CodeChunk


@pytest.fixture
def indexed_chunks():
    """Sample indexed chunks simulating auth and payment codebase."""
    chunk1 = CodeChunk.create(
        repository="synth_repo",
        source_type="code",
        file_path="auth.py",
        symbol_or_heading="class UserSessionManager",
        programming_language="python",
        start_line=22,
        end_line=38,
        content=(
            "class UserSessionManager:\n"
            "    def __init__(self, token_expiry_seconds: int = 3600):\n"
            "        self.expiry = token_expiry_seconds\n"
            "        self.active_sessions: dict[str, str] = {}\n"
        ),
    )
    chunk2 = CodeChunk.create(
        repository="synth_repo",
        source_type="code",
        file_path="payment.py",
        symbol_or_heading="class StripePaymentGateway",
        programming_language="python",
        start_line=21,
        end_line=40,
        content=(
            "class StripePaymentGateway:\n"
            "    def charge_customer(self, customer_id: str, amount_cents: int) -> PaymentInvoice:\n"
            "        ...\n"
        ),
    )
    return [chunk1, chunk2]


# ---------------------------------------------------------------------------
# Test 1: Valid Citations
# ---------------------------------------------------------------------------
def test_assistant_valid_citations(indexed_chunks):
    canned_answer = (
        "**Facts:**\n"
        "- Token expiry is configured in UserSessionManager.__init__ as 3600 seconds [1].\n"
        "**Inferences:**\n"
        "- None."
    )
    mock_llm = MockLLMClient(canned_response=canned_answer)

    response = ask_codebase(
        question="Where is token expiry checked?",
        chunks=indexed_chunks,
        llm_client=mock_llm,
    )

    assert "UserSessionManager" in response.cleaned_answer
    assert "[1]" in response.cleaned_answer
    assert len(response.sources) == 1
    assert response.sources[0].file_path == "auth.py"
    assert response.sources[0].start_line == 22
    assert response.sources[0].end_line == 38
    assert response.invalid_citations == []


# ---------------------------------------------------------------------------
# Test 2: Invented Citations
# ---------------------------------------------------------------------------
def test_assistant_invented_citations(indexed_chunks):
    # Model cites chunk [1], but also invents [99]
    canned_answer = (
        "**Facts:**\n"
        "- Token expiry is 3600 seconds [1].\n"
        "- OAuth2 refresh tokens expire after 30 days [99].\n"
        "**Inferences:**\n"
        "- None."
    )
    mock_llm = MockLLMClient(canned_response=canned_answer)

    response = ask_codebase(
        question="Where is token expiry checked?",
        chunks=indexed_chunks,
        llm_client=mock_llm,
    )

    # Valid citation [1] must remain
    assert "[1]" in response.cleaned_answer
    assert len(response.valid_citations) == 1

    # Invented citation [99] must be flagged and removed from cleaned answer
    assert 99 in response.invalid_citations
    assert "[99]" not in response.cleaned_answer
    assert len(response.sources) == 1
    assert response.sources[0].file_path == "auth.py"


# ---------------------------------------------------------------------------
# Test 3: Empty Retrieval Results
# ---------------------------------------------------------------------------
def test_assistant_empty_retrieval_results():
    mock_llm = MockLLMClient()

    # Query with empty chunks list
    response = ask_codebase(
        question="Where is the Kubernetes cluster defined?",
        chunks=[],
        llm_client=mock_llm,
    )

    assert "Insufficient evidence" in response.cleaned_answer
    assert response.sources == []
    assert response.valid_citations == []
    assert response.invalid_citations == []


# ---------------------------------------------------------------------------
# Test 4: Missing API Key
# ---------------------------------------------------------------------------
def test_assistant_missing_api_key(monkeypatch):
    # Clear all API keys from environment
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    with pytest.raises(MissingAPIKeyError) as exc_info:
        get_llm_client(provider="openai")

    assert "OPENAI_API_KEY environment variable is missing" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 5: LLM Errors
# ---------------------------------------------------------------------------
def test_assistant_llm_errors(indexed_chunks):
    class FailingLLMClient:
        provider_name = "failing"
        model_name = "fail-1"

        def complete(self, prompt: str, system_prompt: str | None = None) -> str:
            raise LLMError("API rate limit exceeded or connection timed out.")

    failing_llm = FailingLLMClient()

    with pytest.raises(LLMError) as exc_info:
        ask_codebase(
            question="Where is token expiry checked?",
            chunks=indexed_chunks,
            llm_client=failing_llm,
        )

    assert "rate limit exceeded" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 6: CLI 'ask' Subcommand
# ---------------------------------------------------------------------------
def test_cli_ask_command(tmp_path: Path, capsys: pytest.CaptureFixture):
    repo_dir = tmp_path / "sample_repo"
    repo_dir.mkdir()
    (repo_dir / "auth.py").write_text(
        "class Session:\n    def __init__(self, expiry=3600):\n        self.expiry = expiry\n",
        encoding="utf-8",
    )

    index_dir = tmp_path / "test_index"

    # Index first
    ret_index = main(["index", str(repo_dir), "--index-dir", str(index_dir)])
    assert ret_index == 0

    canned_answer = (
        "**Facts:**\n"
        "- Session expiry defaults to 3600 [1].\n"
        "**Inferences:**\n"
        "- None."
    )
    mock_llm = MockLLMClient(canned_response=canned_answer)

    with patch("gitcontext.assistant.CodeAssistant.ask") as mock_ask:
        from gitcontext.citations import Citation
        from gitcontext.assistant import AssistantResponse

        mock_ask.return_value = AssistantResponse(
            question="Where is token expiry checked?",
            answer=canned_answer,
            cleaned_answer=canned_answer,
            sources=[
                Citation(
                    source_index=1,
                    file_path="auth.py",
                    symbol_or_heading="class Session",
                    start_line=1,
                    end_line=3,
                    programming_language="python",
                    raw_reference="[1]",
                )
            ],
            valid_citations=[],
            invalid_citations=[],
            evidence_chunks=[],
            model="mock",
            provider="mock",
        )

        ret_ask = main([
            "ask",
            "Where is token expiry checked?",
            "--index-dir",
            str(index_dir),
            "--provider",
            "mock",
        ])
        assert ret_ask == 0

        captured = capsys.readouterr()
        assert "Where is token expiry checked?" in captured.out
        assert "Answer:" in captured.out
        assert "Session expiry defaults to 3600 [1]" in captured.out
        assert "Sources:" in captured.out
        assert "[1] auth.py:L1-L3 (class Session)" in captured.out
