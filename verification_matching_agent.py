from __future__ import annotations

from typing import Any

from agent_tools import ClaudeReasoningTool, MatchingTool, StorageTool, VerificationTool


class VerificationMatchingAgent:
    """Agent 3: verify records, store them, and build match results using tools."""

    def __init__(
        self,
        verification_tool: VerificationTool,
        matching_tool: MatchingTool,
        storage_tool: StorageTool,
        intelligence_tool: ClaudeReasoningTool | None = None,
    ) -> None:
        self.verification_tool = verification_tool
        self.matching_tool = matching_tool
        self.storage_tool = storage_tool
        self.intelligence_tool = intelligence_tool

    def add_review_notes(self, records: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
        """Ask Claude for short verification notes; keep deterministic data unchanged."""
        if not self.intelligence_tool or not self.intelligence_tool.is_configured or not records:
            return records

        compact = [
            {
                "program_name": record.get("program_name", ""),
                "deadline_verified": record.get("deadline_verified", False),
                "eligibility_verified": record.get("eligibility_verified", False),
                "cost_verified": record.get("cost_verified", False),
                "location": record.get("location", ""),
            }
            for record in records[:8]
        ]
        review = self.intelligence_tool.complete_json(
            system="You review data quality for verified program records. Return JSON only.",
            prompt=(
                "For each record, provide a short verification_note based only on the boolean flags and fields. "
                "Return {\"notes\": [{\"program_name\": \"...\", \"verification_note\": \"...\"}]}.\n\n"
                f"Profile: {profile}\nRecords: {compact}"
            ),
            fallback={"notes": []},
        )
        note_map = {}
        if isinstance(review, dict):
            for note in review.get("notes", []):
                if isinstance(note, dict):
                    note_map[note.get("program_name", "")] = note.get("verification_note", "")
        for record in records:
            if record.get("program_name") in note_map:
                record["verification_note"] = note_map[record["program_name"]]
        return records

    def run(self, records: list[dict[str, Any]], profile: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        verified_records = self.verification_tool.run(records, profile)
        verified_records = self.add_review_notes(verified_records, profile)
        self.storage_tool.run(verified_records)
        matches = self.matching_tool.run(verified_records, profile, limit=5)
        return verified_records, matches
