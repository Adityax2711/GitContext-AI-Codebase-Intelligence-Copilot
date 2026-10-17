"""Agent package for GitContext Copilot."""

from gitcontext.agent.orchestrator import (
    AgentOrchestrator,
    AgentRunResult,
    AgentStep,
)
from gitcontext.agent.patch import PatchManager, PatchProposal
from gitcontext.agent.tools import AgentToolRegistry, ToolDefinition

__all__ = [
    "AgentOrchestrator",
    "AgentRunResult",
    "AgentStep",
    "PatchManager",
    "PatchProposal",
    "AgentToolRegistry",
    "ToolDefinition",
]
