from __future__ import annotations

"""Compatibility exports for the split agent architecture.

The real implementation now lives in:
- agent_tools.py
- profile_discovery_agent.py
- program_extraction_agent.py
- verification_matching_agent.py
- orchestrator_agent.py
"""

from agent_tools import (
    FirecrawlClient,
    FirecrawlScrapeTool,
    FirecrawlSearchTool,
    ClaudeReasoningTool,
    MatchingTool,
    SnapshotTool,
    StorageTool,
    VerificationTool,
    compute_pipeline_metrics,
    profile_to_student,
    record_matches_location,
)
from orchestrator_agent import AgenticPipelineResult, PipelineOrchestratorAgent, run_agentic_pipeline
from profile_discovery_agent import ProfileDiscoveryAgent
from program_extraction_agent import ProgramExtractionAgent
from verification_matching_agent import VerificationMatchingAgent


__all__ = [
    "AgenticPipelineResult",
    "FirecrawlClient",
    "FirecrawlScrapeTool",
    "FirecrawlSearchTool",
    "ClaudeReasoningTool",
    "MatchingTool",
    "PipelineOrchestratorAgent",
    "ProfileDiscoveryAgent",
    "ProgramExtractionAgent",
    "SnapshotTool",
    "StorageTool",
    "VerificationMatchingAgent",
    "VerificationTool",
    "compute_pipeline_metrics",
    "profile_to_student",
    "record_matches_location",
    "run_agentic_pipeline",
]
