"""Citation parsing, verification, and formatting module."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union

from gitcontext.models import CodeChunk, SearchResult

# Matches citations like [1], [2], [10], or comma-separated [1, 2, 3]
BRACKET_CITATION_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


@dataclass(frozen=True)
class Citation:
    """Represents a verified citation grounded in a retrieved code chunk."""

    source_index: int
    file_path: str
    symbol_or_heading: str
    start_line: int
    end_line: int
    programming_language: str
    raw_reference: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_index": self.source_index,
            "file_path": self.file_path,
            "symbol_or_heading": self.symbol_or_heading,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "programming_language": self.programming_language,
            "raw_reference": self.raw_reference,
        }


@dataclass
class CitationVerificationResult:
    """Outcome of parsing and validating citations in an answer."""

    original_answer: str
    cleaned_answer: str
    valid_citations: List[Citation]
    invalid_citations: List[int]
    sources: List[Citation]

    @property
    def has_invalid_citations(self) -> bool:
        return len(self.invalid_citations) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_answer": self.original_answer,
            "cleaned_answer": self.cleaned_answer,
            "valid_citations": [c.to_dict() for c in self.valid_citations],
            "invalid_citations": self.invalid_citations,
            "sources": [s.to_dict() for s in self.sources],
            "has_invalid_citations": self.has_invalid_citations,
        }


def extract_citation_indices(text: str) -> List[int]:
    """Extract all integer citation references appearing in bracket notation."""
    indices: List[int] = []
    for match in BRACKET_CITATION_RE.finditer(text):
        group = match.group(1)
        for part in group.split(","):
            part_clean = part.strip()
            if part_clean.isdigit():
                indices.append(int(part_clean))
    return indices


def normalize_evidence_list(
    evidence: Sequence[Union[SearchResult, CodeChunk]]
) -> List[CodeChunk]:
    """Extract raw CodeChunk instances from SearchResult or CodeChunk items."""
    chunks: List[CodeChunk] = []
    for item in evidence:
        if isinstance(item, SearchResult):
            chunks.append(item.chunk)
        elif isinstance(item, CodeChunk):
            chunks.append(item)
        else:
            raise TypeError(f"Expected CodeChunk or SearchResult, got {type(item)}")
    return chunks


def is_valid_chunk_bounds(chunk: CodeChunk) -> bool:
    """Check that a chunk has a valid file path and positive line bounds."""
    if not chunk.file_path or not isinstance(chunk.file_path, str):
        return False
    if not (isinstance(chunk.start_line, int) and isinstance(chunk.end_line, int)):
        return False
    if chunk.start_line < 1 or chunk.end_line < chunk.start_line:
        return False
    return True


def remove_or_flag_invalid_citations(
    text: str,
    invalid_indices: Sequence[int],
    flag_instead_of_remove: bool = False,
) -> str:
    """Sanitize answer text by either stripping or flagging invalid citations."""
    if not invalid_indices:
        return text

    invalid_set = set(invalid_indices)

    def replace_bracket(match: re.Match) -> str:
        group = match.group(1)
        sub_nums = [int(p.strip()) for p in group.split(",") if p.strip().isdigit()]
        valid_nums = [n for n in sub_nums if n not in invalid_set]
        bad_nums = [n for n in sub_nums if n in invalid_set]

        if not valid_nums:
            if flag_instead_of_remove:
                return f"[invalid citation: {', '.join(str(n) for n in bad_nums)}]"
            return ""

        if flag_instead_of_remove and bad_nums:
            return f"[{', '.join(str(n) for n in valid_nums)}] [invalid citation: {', '.join(str(n) for n in bad_nums)}]"

        return f"[{', '.join(str(n) for n in valid_nums)}]"

    cleaned = BRACKET_CITATION_RE.sub(replace_bracket, text)
    # Clean up any leftover double spaces before punctuation
    cleaned = re.sub(r" +([.,;:])", r"\1", cleaned)
    return cleaned.strip()


def verify_citations(
    answer: str,
    evidence: Sequence[Union[SearchResult, CodeChunk]],
    strip_invalid: bool = True,
) -> CitationVerificationResult:
    """Parse citations in the answer, verify them against evidence chunks, and compile sources."""
    chunks = normalize_evidence_list(evidence)
    total_chunks = len(chunks)

    parsed_indices = extract_citation_indices(answer)

    valid_citations: List[Citation] = []
    invalid_citations: List[int] = []
    seen_sources: Dict[int, Citation] = {}

    for idx in parsed_indices:
        if 1 <= idx <= total_chunks:
            chunk = chunks[idx - 1]
            if is_valid_chunk_bounds(chunk):
                citation = Citation(
                    source_index=idx,
                    file_path=chunk.file_path,
                    symbol_or_heading=chunk.symbol_or_heading,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    programming_language=chunk.programming_language,
                    raw_reference=f"[{idx}]",
                )
                valid_citations.append(citation)
                if idx not in seen_sources:
                    seen_sources[idx] = citation
                continue

        # If not valid or out of range
        if idx not in invalid_citations:
            invalid_citations.append(idx)

    # Sort unique sources by citation index
    unique_sources = sorted(seen_sources.values(), key=lambda c: c.source_index)

    cleaned_answer = (
        remove_or_flag_invalid_citations(answer, invalid_citations, flag_instead_of_remove=False)
        if strip_invalid
        else answer
    )

    return CitationVerificationResult(
        original_answer=answer,
        cleaned_answer=cleaned_answer,
        valid_citations=valid_citations,
        invalid_citations=invalid_citations,
        sources=unique_sources,
    )


def format_sources_list(sources: Sequence[Citation]) -> str:
    """Format verified sources list for CLI or human display."""
    if not sources:
        return "  (No citations found)"

    lines: List[str] = []
    for s in sources:
        symbol_desc = f" ({s.symbol_or_heading})" if s.symbol_or_heading else ""
        lines.append(
            f"  [{s.source_index}] {s.file_path}:L{s.start_line}-L{s.end_line}{symbol_desc}"
        )
    return "\n".join(lines)
