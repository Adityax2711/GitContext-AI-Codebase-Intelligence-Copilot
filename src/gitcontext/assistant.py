"""Core codebase assistant orchestration, independent of the CLI (FastAPI reusable)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from gitcontext.citations import (
    Citation,
    CitationVerificationResult,
    format_sources_list,
    verify_citations,
)
from gitcontext.generation import generate_answer
from gitcontext.indexing import get_default_index_dir, load_index
from gitcontext.llm import LLMClient
from gitcontext.models import CodeChunk, SearchResult
from gitcontext.retrieval import hybrid_search


@dataclass
class AssistantResponse:
    """Complete structured response from the codebase assistant."""

    question: str
    answer: str
    cleaned_answer: str
    sources: List[Citation]
    valid_citations: List[Citation]
    invalid_citations: List[int]
    evidence_chunks: List[CodeChunk]
    model: str
    provider: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary for FastAPI or JSON serialization."""
        return {
            "question": self.question,
            "answer": self.answer,
            "cleaned_answer": self.cleaned_answer,
            "sources": [s.to_dict() for s in self.sources],
            "valid_citations": [c.to_dict() for c in self.valid_citations],
            "invalid_citations": self.invalid_citations,
            "evidence_chunks": [c.to_dict() for c in self.evidence_chunks],
            "model": self.model,
            "provider": self.provider,
        }

    def format_cli_output(self) -> str:
        """Format human-readable CLI output with Answer, Sources, and any warnings."""
        sections = [f"Question: {self.question}\n", "Answer:", self.cleaned_answer, "\nSources:", format_sources_list(self.sources)]

        if self.invalid_citations:
            bad_list = ", ".join(f"[{i}]" for i in self.invalid_citations)
            sections.append(f"\nWarning: The following unverified citations were flagged: {bad_list}")

        return "\n".join(sections)


class CodeAssistant:
    """Reusable assistant service for querying codebases."""

    def __init__(
        self,
        index_dir: Optional[Path] = None,
        llm_client: Optional[LLMClient] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.index_dir = index_dir or get_default_index_dir()
        self.llm_client = llm_client
        self.provider = provider
        self.model = model

    def ask(
        self,
        question: str,
        top_k: int = 5,
        chunks: Optional[List[CodeChunk]] = None,
    ) -> AssistantResponse:
        """Answer question with grounded citations using index or pre-supplied chunks."""
        q_clean = question.strip()
        if not q_clean:
            return AssistantResponse(
                question=question,
                answer="Error: Question cannot be empty.",
                cleaned_answer="Error: Question cannot be empty.",
                sources=[],
                valid_citations=[],
                invalid_citations=[],
                evidence_chunks=[],
                model="none",
                provider="internal",
            )

        # 1. Load chunks if not directly provided
        if chunks is None:
            loaded_chunks, _ = load_index(self.index_dir)
            active_chunks = loaded_chunks
        else:
            active_chunks = chunks

        if not active_chunks:
            msg = (
                "Insufficient evidence: No codebase index found or index is empty. "
                "Please index a repository first using 'python -m gitcontext index <repo_path>'."
            )
            return AssistantResponse(
                question=question,
                answer=msg,
                cleaned_answer=msg,
                sources=[],
                valid_citations=[],
                invalid_citations=[],
                evidence_chunks=[],
                model="none",
                provider="internal",
            )

        # 2. Hybrid Retrieval
        retrieval_results = hybrid_search(query=q_clean, chunks=active_chunks, top_k=top_k)

        if not retrieval_results:
            msg = "Insufficient evidence: No relevant code chunks were retrieved for the question."
            return AssistantResponse(
                question=question,
                answer=msg,
                cleaned_answer=msg,
                sources=[],
                valid_citations=[],
                invalid_citations=[],
                evidence_chunks=[],
                model="none",
                provider="internal",
            )

        # 3. Generation via LLM
        gen_result = generate_answer(
            question=q_clean,
            evidence=retrieval_results,
            llm_client=self.llm_client,
            provider=self.provider,
            model=self.model,
        )

        # 4. Citations parsing and verification
        verification = verify_citations(
            answer=gen_result.raw_answer,
            evidence=retrieval_results,
            strip_invalid=True,
        )

        return AssistantResponse(
            question=question,
            answer=verification.original_answer,
            cleaned_answer=verification.cleaned_answer,
            sources=verification.sources,
            valid_citations=verification.valid_citations,
            invalid_citations=verification.invalid_citations,
            evidence_chunks=[r.chunk for r in retrieval_results],
            model=gen_result.model,
            provider=gen_result.provider,
        )


def ask_codebase(
    question: str,
    index_dir: Optional[Path] = None,
    top_k: int = 5,
    llm_client: Optional[LLMClient] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    chunks: Optional[List[CodeChunk]] = None,
) -> AssistantResponse:
    """Convenience function to query codebase and get grounded response with citations."""
    assistant = CodeAssistant(
        index_dir=index_dir,
        llm_client=llm_client,
        provider=provider,
        model=model,
    )
    return assistant.ask(question=question, top_k=top_k, chunks=chunks)
