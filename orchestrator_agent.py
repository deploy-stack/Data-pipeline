from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

# High-level orchestration of the pipeline's discovery, extraction, and verification stages.
from agent_tools import (
    ClaudeReasoningTool,
    FirecrawlClient,
    FirecrawlScrapeTool,
    FirecrawlSearchTool,
    MatchingTool,
    SnapshotTool,
    StorageTool,
    VerificationTool,
    compute_pipeline_metrics,
    profile_to_student,
)
from match import rank_programs
from profile_discovery_agent import ProfileDiscoveryAgent
from program_extraction_agent import ProgramExtractionAgent
from schema import Program
from verification_matching_agent import VerificationMatchingAgent

logger = logging.getLogger(__name__)


@dataclass
class AgenticPipelineResult:
    profile: dict[str, Any]
    sources: list[dict[str, Any]]
    records: list[dict[str, Any]]
    matches: list[dict[str, Any]]
    used_firecrawl: bool
    messages: list[str]
    metrics: dict[str, int]


class PipelineOrchestratorAgent:
    """Orchestrator agent: runs handoffs between discovery, extraction, and verification agents."""

    def __init__(self, client: FirecrawlClient | None = None) -> None:
        self.client = client or FirecrawlClient()
        self.intelligence_tool = ClaudeReasoningTool()
        self.snapshot_tool = SnapshotTool()
        self.verification_tool = VerificationTool()
        self.matching_tool = MatchingTool()
        self.storage_tool = StorageTool()

    def run(
        self,
        profile: dict[str, Any],
        *,
        use_firecrawl: bool = True,
        source_limit: int = 6,
        extraction_limit: int = 5,
        batch_size: int = 10,  # New parameter for batching large source sets
    ) -> AgenticPipelineResult:
        logger.info("Starting agentic pipeline orchestration")
        messages = []

        if use_firecrawl and not self.client.is_configured:
            raise RuntimeError("FIRECRAWL_API_KEY is missing. Add it to .env to explore the internet.")

        if not use_firecrawl:
            logger.info("Firecrawl disabled, using snapshot data")
            records = self.snapshot_tool.run(source_limit)
            verified_records = self.verification_tool.run(records, profile)
            self.storage_tool.run(verified_records)
            programs = [Program.from_dict(record) for record in verified_records]
            matches = rank_programs(programs, profile_to_student(profile), limit=5)
            messages.append("SnapshotTool loaded bundled data because Firecrawl was disabled.")
            metrics = compute_pipeline_metrics(verified_records, sources_explored=len(records))
            logger.info("Agentic pipeline completed using snapshot data")
            return AgenticPipelineResult(profile, [], verified_records, matches, False, messages, metrics)

        logger.info("Initializing agent tools for live data processing")
        discovery_agent = ProfileDiscoveryAgent(FirecrawlSearchTool(self.client), self.intelligence_tool)
        extraction_agent = ProgramExtractionAgent(FirecrawlScrapeTool(self.client), self.intelligence_tool)
        verification_agent = VerificationMatchingAgent(
            self.verification_tool,
            self.matching_tool,
            self.storage_tool,
            self.intelligence_tool,
        )

        if self.intelligence_tool.is_configured:
            messages.append("Claude Haiku 4.5 intelligence tool enabled for query planning, normalization, and verification notes.")
        else:
            messages.append("Claude key not found; agents used deterministic fallbacks for intelligence steps.")

        logger.info("Handoff 1: Orchestrator -> ProfileDiscoveryAgent")
        messages.append("Handoff 1: Orchestrator -> ProfileDiscoveryAgent.")
        sources = discovery_agent.run(profile, limit=source_limit)
        messages.append(f"ProfileDiscoveryAgent returned {len(sources)} candidate sources.")
        logger.info(f"Discovery phase completed: {len(sources)} sources found")

        # Filter sources for relevance if we have many
        if len(sources) > batch_size and self.intelligence_tool.is_configured:
            logger.info(f"Filtering {len(sources)} sources for relevance using Claude")
            sources = self._filter_sources(sources, profile, max_sources=source_limit)
            messages.append(f"Filtered sources down to {len(sources)} most relevant.")
            logger.info(f"Source filtering completed: {len(sources)} sources after filtering")

        logger.info("Handoff 2: Orchestrator -> ProgramExtractionAgent")
        messages.append("Handoff 2: Orchestrator -> ProgramExtractionAgent.")
        
        # Process sources in batches to handle large numbers efficiently
        all_records = []
        for i in range(0, len(sources), batch_size):
            batch = sources[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1} with {len(batch)} sources")
            batch_records = extraction_agent.run(batch, profile, limit=len(batch))
            all_records.extend(batch_records)
            messages.append(f"Batch {i//batch_size + 1}: extracted {len(batch_records)} records.")
        
        records = all_records[:extraction_limit] if extraction_limit else all_records
        messages.append(f"ProgramExtractionAgent returned {len(records)} structured records.")
        logger.info(f"Extraction phase completed: {len(records)} records extracted from {len(sources)} sources")

        logger.info("Handoff 3: Orchestrator -> VerificationMatchingAgent")
        messages.append("Handoff 3: Orchestrator -> VerificationMatchingAgent.")
        verified_records, matches = verification_agent.run(records, profile)
        messages.append(f"VerificationMatchingAgent verified {len(verified_records)} records and built matches.")
        logger.info(f"Verification and matching phase completed: {len(verified_records)} verified records")

        metrics = compute_pipeline_metrics(verified_records, sources_explored=len(sources))
        logger.info("Agentic pipeline orchestration completed successfully")
        return AgenticPipelineResult(profile, sources, verified_records, matches, True, messages, metrics)

    def _filter_sources(self, sources: list[dict[str, Any]], profile: dict[str, Any], max_sources: int = 20) -> list[dict[str, Any]]:
        """Filter sources for relevance using Claude to avoid processing irrelevant URLs."""
        if not sources:
            return sources
        
        # Prepare source descriptions for Claude
        source_descriptions = []
        for i, source in enumerate(sources):
            desc = f"{i+1}. Title: {source.get('title', 'No title')}\n   Description: {source.get('description', 'No description')}\n   URL: {source['url']}"
            source_descriptions.append(desc)
        
        prompt = f"""
        Given this student profile:
        - Grade: {profile.get('grade')}
        - Interests: {', '.join(profile.get('interests', []))}
        - Preferred modality: {profile.get('preferred_modality')}
        - Budget max: ${profile.get('budget_max')}

        Here are {len(sources)} potential program sources. Select the top {max_sources} most relevant ones for pre-college programs that match this student's profile.

        Sources:
        {chr(10).join(source_descriptions)}

        Return a JSON array of indices (1-based) of the most relevant sources, in order of relevance. Return at most {max_sources} indices.
        """
        
        response = self.intelligence_tool.complete_json(
            system="You are a helpful assistant that filters web sources for relevance to student program matching.",
            prompt=prompt,
            fallback=list(range(1, min(len(sources), max_sources) + 1)),
        )
        
        if isinstance(response, list) and response:
            selected_indices = [int(idx) - 1 for idx in response if isinstance(idx, (int, str)) and 0 <= int(idx) - 1 < len(sources)]
            return [sources[i] for i in selected_indices[:max_sources]]
        else:
            # Fallback to first max_sources
            return sources[:max_sources]


def run_agentic_pipeline(
    profile: dict[str, Any],
    *,
    use_firecrawl: bool = True,
    source_limit: int = 6,
    extraction_limit: int = 5,
    batch_size: int = 10,
) -> AgenticPipelineResult:
    orchestrator = PipelineOrchestratorAgent()
    return orchestrator.run(
        profile,
        use_firecrawl=use_firecrawl,
        source_limit=source_limit,
        extraction_limit=extraction_limit,
        batch_size=batch_size,
    )
