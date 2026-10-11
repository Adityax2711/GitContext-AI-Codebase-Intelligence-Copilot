"""GitContext: AI-powered codebase intelligence copilot."""

from gitcontext.assistant import AssistantResponse, CodeAssistant, ask_codebase
from gitcontext.citations import Citation, CitationVerificationResult, verify_citations
from gitcontext.generation import GenerationResult, generate_answer
from gitcontext.llm import LLMClient, LLMError, MissingAPIKeyError, get_llm_client
from gitcontext.models import CodeChunk, IndexMetadata, SearchResult

from gitcontext.bug_models import (
    BugFinding,
    BugInvestigationReport,
    CallTraceInfo,
    StaticAnalysisFinding,
    TestExecutionSummary,
    TestFailure,
)
from gitcontext.investigator import BugInvestigator, investigate_codebase

__version__ = "0.2.0"

__all__ = [
    "CodeChunk",
    "SearchResult",
    "IndexMetadata",
    "LLMClient",
    "LLMError",
    "MissingAPIKeyError",
    "get_llm_client",
    "GenerationResult",
    "generate_answer",
    "Citation",
    "CitationVerificationResult",
    "verify_citations",
    "AssistantResponse",
    "CodeAssistant",
    "ask_codebase",
    "BugFinding",
    "BugInvestigationReport",
    "CallTraceInfo",
    "StaticAnalysisFinding",
    "TestExecutionSummary",
    "TestFailure",
    "BugInvestigator",
    "investigate_codebase",
]
