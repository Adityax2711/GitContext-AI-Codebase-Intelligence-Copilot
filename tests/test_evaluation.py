"""Tests for citation evaluation suite using synthetic repo fixture."""

from pathlib import Path
import pytest
from gitcontext.evaluation import run_evaluation
from gitcontext.indexing import index_repository


def test_citation_evaluation_suite(tmp_path: Path):
    fixture_repo = Path("fixtures") / "synthetic_repo"
    dataset_file = Path("fixtures") / "evaluation_dataset.json"

    assert fixture_repo.exists(), "fixtures/synthetic_repo should exist"
    assert dataset_file.exists(), "fixtures/evaluation_dataset.json should exist"

    # Index the synthetic repo into a temporary directory
    index_dir = tmp_path / "eval_index"
    index_repository(repo_path=fixture_repo, index_dir=index_dir)

    # Run evaluation
    report = run_evaluation(dataset_path=dataset_file, index_dir=index_dir)
    print("\n" + report.summary())

    # Verify results
    assert report.total_questions == 5
    assert report.avg_precision >= 0.8
    assert report.avg_recall >= 0.8
    assert report.citation_validity_rate == 1.0  # 100% valid citations, 0% hallucinations
    assert report.insufficient_evidence_accuracy == 1.0  # Unanswerable correctly flagged
