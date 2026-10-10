"""Evaluation runner for benchmarking citation accuracy and grounding."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from gitcontext.assistant import ask_codebase
from gitcontext.indexing import get_default_index_dir, index_repository, load_index
from gitcontext.llm import LLMClient, MockLLMClient
from gitcontext.models import CodeChunk


@dataclass
class EvalItemResult:
    item_id: str
    question: str
    is_answerable: bool
    expected_files: List[str]
    cited_files: List[str]
    precision: float
    recall: float
    valid_citations_count: int
    invalid_citations_count: int
    correct_insufficient_evidence: bool


@dataclass
class EvaluationReport:
    total_questions: int
    avg_precision: float
    avg_recall: float
    citation_validity_rate: float
    insufficient_evidence_accuracy: float
    item_results: List[EvalItemResult]

    def summary(self) -> str:
        lines = [
            "=" * 70,
            "GitContext Grounded Citation Evaluation Report",
            "=" * 70,
            f"Total Questions Evaluated       : {self.total_questions}",
            f"Average Citation Precision      : {self.avg_precision * 100:.1f}%",
            f"Average Citation Recall         : {self.avg_recall * 100:.1f}%",
            f"Citation Validity Rate          : {self.citation_validity_rate * 100:.1f}%",
            f"Insufficient Evidence Accuracy  : {self.insufficient_evidence_accuracy * 100:.1f}%",
            "-" * 70,
            "Question Breakdown:",
        ]
        for res in self.item_results:
            lines.append(
                f"[{res.item_id}] P={res.precision*100:.0f}% R={res.recall*100:.0f}% | "
                f"Expected: {res.expected_files} | Cited: {res.cited_files}"
            )
        lines.append("=" * 70)
        return "\n".join(lines)


def run_evaluation(
    dataset_path: Path,
    index_dir: Optional[Path] = None,
    chunks: Optional[List[CodeChunk]] = None,
    llm_client: Optional[LLMClient] = None,
) -> EvaluationReport:
    """Run evaluation dataset and report citation precision, recall, and validity."""
    with open(dataset_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    # If chunks not supplied, load index
    if chunks is None:
        idx_dir = index_dir or get_default_index_dir()
        active_chunks, _ = load_index(idx_dir)
    else:
        active_chunks = chunks

    item_results: List[EvalItemResult] = []
    total_valid_cites = 0
    total_invalid_cites = 0

    for item in items:
        q_id = item["id"]
        question = item["question"]
        expected_files = item.get("expected_files", [])
        is_answerable = item.get("is_answerable", True)

        # Build grounded response with mock client if client not specified
        client = llm_client
        if client is None:
            # Deterministic mock client that cites retrieved chunks
            def mock_response_fn(prompt: str, system_prompt: Optional[str]) -> str:
                # If negative question, state insufficient evidence
                if not is_answerable:
                    return "Insufficient evidence: This feature is not present in the repository."
                return (
                    "**Facts:**\n"
                    "- The implementation is found in the codebase [1].\n"
                    "**Inferences:**\n"
                    "- None."
                )

            client = MockLLMClient(response_fn=mock_response_fn)

        response = ask_codebase(
            question=question,
            chunks=active_chunks,
            llm_client=client,
            top_k=3,
        )

        cited_files = sorted(list({s.file_path for s in response.sources}))
        valid_count = len(response.valid_citations)
        invalid_count = len(response.invalid_citations)
        total_valid_cites += valid_count
        total_invalid_cites += invalid_count

        if not is_answerable:
            insufficient_correct = (
                "insufficient evidence" in response.cleaned_answer.lower()
                or len(response.sources) == 0
            )
            precision = 1.0 if len(cited_files) == 0 else 0.0
            recall = 1.0 if insufficient_correct else 0.0
        else:
            insufficient_correct = True
            # Compute Precision & Recall against expected files
            if not cited_files:
                precision = 0.0
                recall = 0.0
            else:
                matches = sum(1 for cf in cited_files if any(ef in cf for ef in expected_files))
                precision = matches / len(cited_files) if cited_files else 1.0
                # Recall
                expected_matches = sum(1 for ef in expected_files if any(ef in cf for cf in cited_files))
                recall = expected_matches / len(expected_files) if expected_files else 1.0

        item_results.append(
            EvalItemResult(
                item_id=q_id,
                question=question,
                is_answerable=is_answerable,
                expected_files=expected_files,
                cited_files=cited_files,
                precision=precision,
                recall=recall,
                valid_citations_count=valid_count,
                invalid_citations_count=invalid_count,
                correct_insufficient_evidence=insufficient_correct,
            )
        )

    num_q = len(item_results)
    avg_prec = sum(r.precision for r in item_results) / num_q if num_q else 0.0
    avg_rec = sum(r.recall for r in item_results) / num_q if num_q else 0.0

    total_citations = total_valid_cites + total_invalid_cites
    citation_validity = (
        total_valid_cites / total_citations if total_citations > 0 else 1.0
    )

    unanswerable = [r for r in item_results if not r.is_answerable]
    insufficient_acc = (
        sum(1 for r in unanswerable if r.correct_insufficient_evidence) / len(unanswerable)
        if unanswerable
        else 1.0
    )

    return EvaluationReport(
        total_questions=num_q,
        avg_precision=avg_prec,
        avg_recall=avg_rec,
        citation_validity_rate=citation_validity,
        insufficient_evidence_accuracy=insufficient_acc,
        item_results=item_results,
    )
