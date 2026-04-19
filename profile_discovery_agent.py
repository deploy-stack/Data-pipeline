from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_tools import FIRECRAWL_SOURCES_PATH, ClaudeReasoningTool, FirecrawlSearchTool


class ProfileDiscoveryAgent:
    """Agent 1: collect profile intent and discover sources with a search tool."""

    def __init__(self, search_tool: FirecrawlSearchTool, intelligence_tool: ClaudeReasoningTool | None = None) -> None:
        self.search_tool = search_tool
        self.intelligence_tool = intelligence_tool

    def build_queries(self, profile: dict[str, Any]) -> list[str]:
        interests = " ".join(profile.get("interests", []))
        modality = profile.get("preferred_modality", "any")
        grade = profile.get("grade")
        location = profile.get("location_preference", "")
        radius = profile.get("radius_miles", "")
        online_phrase = "online or virtual" if profile.get("include_online", True) else ""
        location_phrase = f"near {location} within {radius} miles" if location else ""
        fallback_queries = [
            (
                "official high school pre-college summer program "
                f"{interests} grade {grade} {modality} {online_phrase} {location_phrase} "
                "application deadline eligibility cost"
            ),
            (
                "official summer research program high school students "
                f"{interests} grade {grade} {modality} {location_phrase} cost deadline"
            ),
            (
                "official academic enrichment program high school "
                f"{interests} {modality} {online_phrase} {location_phrase} application deadline tuition"
            ),
        ]
        if not self.intelligence_tool or not self.intelligence_tool.is_configured:
            return fallback_queries

        response = self.intelligence_tool.complete_json(
            system="You plan web search queries for an agentic education-data pipeline. Return JSON only.",
            prompt=(
                "Create 3 concise web search queries to find official pre-college, summer, research, "
                "or enrichment programs for this student profile. Avoid naming specific schools unless "
                "the profile explicitly names one. Return JSON as {\"queries\": [..]}.\n\n"
                f"Profile: {json.dumps(profile)}"
            ),
            fallback={"queries": fallback_queries},
        )
        queries = response.get("queries", fallback_queries) if isinstance(response, dict) else fallback_queries
        return [str(query) for query in queries[:3] if str(query).strip()] or fallback_queries

    def run(self, profile: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
        seen = set()
        sources = []
        for query in self.build_queries(profile):
            if len(sources) >= limit:
                break
            results = self.search_tool.run(query, limit=limit)
            for result in results:
                if len(sources) >= limit:
                    break
                url = result.get("url")
                if not url or url in seen:
                    continue
                seen.add(url)
                sources.append(
                    {
                        "url": url,
                        "title": result.get("title", ""),
                        "description": result.get("description", ""),
                        "query": query,
                    }
                )

        Path(FIRECRAWL_SOURCES_PATH).parent.mkdir(exist_ok=True)
        FIRECRAWL_SOURCES_PATH.write_text(json.dumps(sources, indent=2), encoding="utf-8")
        return sources
