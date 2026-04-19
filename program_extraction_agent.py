from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from agent_tools import ClaudeReasoningTool, FirecrawlScrapeTool


class ProgramExtractionAgent:
    """Agent 2: extract structured program attributes with a scraping tool."""

    def __init__(self, scrape_tool: FirecrawlScrapeTool, intelligence_tool: ClaudeReasoningTool | None = None) -> None:
        self.scrape_tool = scrape_tool
        self.intelligence_tool = intelligence_tool

    def normalize_record(self, record: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        """Use Claude to lightly normalize extracted fields when available."""
        if not self.intelligence_tool or not self.intelligence_tool.is_configured:
            return record

        required_fields = [
            "eligibility_requirements",
            "application_deadline",
            "budget",
            "program_type",
            "location",
            "provider",
            "duration",
            "program_name",
            "subject_areas",
            "source_url",
            "cost",
            "modality",
            "application_link",
        ]
        normalized = self.intelligence_tool.complete_json(
            system=(
                "You normalize extracted pre-college program data. Return JSON only. "
                "Do not invent facts; preserve empty strings when not explicit."
            ),
            prompt=(
                "Normalize this extracted record for matching. Keep these fields if possible: "
                f"{', '.join(required_fields)}. Ensure program_type is online, in_person, hybrid, or empty. "
                "Ensure subject_areas is a list. Return a single JSON object.\n\n"
                f"Student profile: {profile}\n\nRecord: {record}"
            ),
            fallback=record,
        )
        if not isinstance(normalized, dict):
            return record
        for key, value in record.items():
            normalized.setdefault(key, value)
        return normalized

    def _scrape_and_normalize(self, source: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        """Scrape and normalize a single source, handling exceptions."""
        try:
            record = self.scrape_tool.run(source["url"], profile)
            return self.normalize_record(record, profile)
        except Exception as exc:
            return {
                "program_name": source.get("title") or source["url"],
                "source_url": source["url"],
                "short_description": source.get("description", ""),
                "raw_text_snippet": str(exc)[:400],
                "source": "firecrawl_error",
            }

    def run(self, sources: list[dict[str, Any]], profile: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
        records = []
        sources_to_process = sources[:limit]
        
        # Use parallel processing for scraping to improve performance
        with ThreadPoolExecutor(max_workers=min(len(sources_to_process), 5)) as executor:
            future_to_source = {
                executor.submit(self._scrape_and_normalize, source, profile): source 
                for source in sources_to_process
            }
            for future in as_completed(future_to_source):
                records.append(future.result())
        
        return records
