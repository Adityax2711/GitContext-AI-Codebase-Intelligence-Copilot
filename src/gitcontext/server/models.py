"""Pydantic request and response models for FastAPI endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class RepositorySelectRequest(BaseModel):
    repository_path: str = Field(..., description="Local path to repository directory")
    reindex: bool = Field(default=False, description="Whether to reindex repository on select")


class FileReadRequest(BaseModel):
    file_path: str = Field(..., description="Repository-relative file path")
    start_line: Optional[int] = Field(default=None, ge=1)
    end_line: Optional[int] = Field(default=None, ge=1)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., description="User query or instruction")
    history: Optional[List[ChatMessage]] = Field(default_factory=list)
    repository_path: Optional[str] = Field(default=None, description="Optional override repository path")


class InvestigateRequest(BaseModel):
    query: str = Field(..., description="Bug description, error message, or symptom")
    target_file: Optional[str] = None
    target_symbol: Optional[str] = None
    run_tests: bool = True
    test_path: Optional[str] = None


class PatchActionRequest(BaseModel):
    patch_id: str = Field(..., description="ID of patch to apply, reject, or test")
    test_path: Optional[str] = None


class RunTestRequest(BaseModel):
    test_path: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
