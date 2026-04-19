from __future__ import annotations

import csv
import json
import logging
import os
from pathlib import Path
from typing import Any

from match import rank_programs
from program_database import save_verified_records
from schema import Program, StudentProfile
from verify import verify_record

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


FIRECRAWL_BASE_URL = "https://api.firecrawl.dev/v2"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_HAIKU_MODEL = "claude-haiku-4-5-20251001"
DATA_DIR = Path("data")
FIRECRAWL_SOURCES_PATH = DATA_DIR / "firecrawl_sources.json"
FIRECRAWL_PROGRAMS_JSON_PATH = DATA_DIR / "firecrawl_programs.json"
FIRECRAWL_PROGRAMS_CSV_PATH = DATA_DIR / "firecrawl_programs.csv"


PROGRAM_SCHEMA = {
    "type": "object",
    "properties": {
        "eligibility_requirements": {"type": "string"},
        "application_deadline": {"type": "string"},
        "budget": {"type": "string", "description": "Program cost or budget requirement"},
        "program_type": {"type": "string", "description": "online, in_person, or hybrid"},
        "provider": {"type": "string"},
        "duration": {"type": "string"},
        "program_name": {"type": "string"},
        "short_description": {"type": "string"},
        "subject_areas": {"type": "array", "items": {"type": "string"}},
        "modality": {"type": "string", "description": "online, in_person, or hybrid"},
        "location": {"type": "string"},
        "grades_or_age_eligibility": {"type": "string"},
        "program_dates": {"type": "string"},
        "cost": {"type": "string"},
        "application_link": {"type": "string"},
    },
    "required": [
        "eligibility_requirements",
        "application_deadline",
        "budget",
        "program_type",
        "location",
        "provider",
        "duration",
        "program_name",
    ],
}


CSV_FIELDS = [
    "eligibility_requirements",
    "application_deadline",
    "budget",
    "program_type",
    "location",
    "provider",
    "duration",
    "program_name",
    "source_url",
    "subjects",
    "subject_areas",
    "modality",
    "grades_or_age_eligibility",
    "program_dates",
    "cost",
    "cost_numeric",
    "deadline_verified",
    "eligibility_verified",
    "cost_verified",
    "extraction_confidence",
    "confidence_score",
    "completeness_score",
    "raw_text_snippet",
    "last_checked",
    "source",
]


def load_dotenv_if_available() -> None:
    """Load .env without making python-dotenv mandatory for offline demos."""
    logger.info("Attempting to load API keys from environment")
    try:
        from dotenv import load_dotenv
        logger.info("Using python-dotenv to load .env file")
        load_dotenv()
    except ImportError:
        env_path = Path(".env")
        if not env_path.exists():
            logger.info("No .env file found and python-dotenv not available, using environment variables")
            return
        logger.info("Loading API keys from .env file manually")
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
        logger.info("API keys loaded from .env file manually")
    load_dotenv()


def profile_to_student(profile: dict[str, Any]) -> StudentProfile:
    return StudentProfile(
        grade=int(profile.get("grade", 11)),
        interests=list(profile.get("interests", [])),
        preferred_modality=str(profile.get("preferred_modality", "online")),
        budget_max=int(profile.get("budget_max", 4000)),
    )


def record_matches_location(record: dict[str, Any], profile: dict[str, Any]) -> bool:
    """Location gate: online allowed anywhere, in-person requires location match within radius."""
    program_type = str(record.get("program_type") or record.get("modality", "")).lower()
    location = str(record.get("location", "")).lower()
    include_online = bool(profile.get("include_online", True))
    requested_location = str(profile.get("location_preference", "")).strip().lower()
    is_online = "online" in program_type or "online" in location or "virtual" in location
    
    # Online programs can be attended from anywhere
    if include_online and is_online:
        return True
    
    # For in-person programs, require location match
    if not is_online:
        if not requested_location:
            logger.info(f"In-person program '{record.get('program_name')}' filtered: no location preference set")
            return False
        tokens = [token for token in requested_location.replace(",", " ").split() if len(token) > 2]
        matches = any(token in location for token in tokens)
        if not matches:
            logger.info(f"In-person program '{record.get('program_name')}' at '{location}' does not match requested location '{requested_location}'")
        return matches
    
    # If online not included, reject non-online programs
    return False


def compute_pipeline_metrics(records: list[dict[str, Any]], sources_explored: int) -> dict[str, int]:
    required_attrs = [
        "eligibility_requirements",
        "application_deadline",
        "budget",
        "program_type",
        "location",
        "provider",
        "duration",
        "program_name",
    ]
    data_points = sum(1 for record in records for field in required_attrs if record.get(field))
    verified = sum(1 for record in records if record.get("eligibility_verified") or record.get("deadline_verified"))
    return {
        "sources_explored": sources_explored,
        "data_points_extracted": data_points,
        "records_verified_against_user_details": verified,
    }


class FirecrawlClient:
    """Low-level HTTP tool wrapper used by Firecrawl search/scrape tools."""

    def __init__(self, api_key: str | None = None) -> None:
        load_dotenv_if_available()
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY")
        logger.info(f"FirecrawlClient initialized with API key: {'present' if self.api_key else 'missing'}")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        import requests

        if not self.api_key:
            raise RuntimeError("FIRECRAWL_API_KEY is missing. Add it to .env to run the live pipeline.")
        response = requests.post(
            f"{FIRECRAWL_BASE_URL}{path}",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()


class ClaudeReasoningTool:
    """Tool: small Claude Haiku 4.5 calls for agent planning and cleanup."""

    def __init__(self, api_key: str | None = None, model: str = CLAUDE_HAIKU_MODEL) -> None:
        load_dotenv_if_available()
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        self.model = model
        logger.info(f"ClaudeReasoningTool initialized with API key: {'present' if self.api_key else 'missing'}, model: {self.model}")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def complete_text(self, system: str, prompt: str, max_tokens: int = 700) -> str:
        import requests

        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY or CLAUDE_API_KEY is missing in .env.")
        response = requests.post(
            ANTHROPIC_BASE_URL,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()
        return "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")

    def complete_json(self, system: str, prompt: str, fallback: Any) -> Any:
        try:
            text = self.complete_text(system, prompt)
            start = text.find("{")
            list_start = text.find("[")
            if list_start != -1 and (start == -1 or list_start < start):
                start = list_start
            end = max(text.rfind("}"), text.rfind("]"))
            if start == -1 or end == -1:
                return fallback
            return json.loads(text[start : end + 1])
        except Exception:
            return fallback


class FirecrawlSearchTool:
    """Tool: search the open web with Firecrawl."""

    def __init__(self, client: FirecrawlClient) -> None:
        self.client = client

    def run(self, query: str, limit: int = 6) -> list[dict[str, Any]]:
        payload = {
            "query": query,
            "limit": limit,
            "sources": ["web"],
            "country": "US",
            "ignoreInvalidURLs": True,
            "timeout": 60000,
        }
        data = self.client.post("/search", payload)
        results = data.get("data", {}).get("web", data.get("data", []))
        return results if isinstance(results, list) else []


class FirecrawlScrapeTool:
    """Tool: scrape one URL and extract program JSON using Firecrawl."""

    def __init__(self, client: FirecrawlClient) -> None:
        self.client = client
        self.cache_file = DATA_DIR / "scrape_cache.json"
        self.cache = self._load_cache()

    def _load_cache(self) -> dict:
        """Load persistent cache from file."""
        if self.cache_file.exists():
            try:
                return json.loads(self.cache_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_cache(self) -> None:
        """Save cache to file."""
        DATA_DIR.mkdir(exist_ok=True)
        self.cache_file.write_text(json.dumps(self.cache, indent=2), encoding="utf-8")

    def run(self, url: str, profile: dict[str, Any]) -> dict[str, Any]:
        # Check persistent cache first
        if url in self.cache:
            logger.info(f"Using cached data for URL: {url}")
            return self.cache[url]
        
        prompt = (
            "Extract one pre-college, summer, research, or academic enrichment program "
            "for high school students. Prioritize fields that help match this student: "
            f"grade {profile.get('grade')}, interests {', '.join(profile.get('interests', []))}, "
            f"preferred modality {profile.get('preferred_modality')}, budget {profile.get('budget_max')}. "
            "Return empty strings when a field is not explicit on the page."
        )
        payload = {
            "url": url,
            "formats": ["markdown", {"type": "json", "schema": PROGRAM_SCHEMA, "prompt": prompt}],
            "onlyMainContent": True,
            "timeout": 60000,  # Reduced from 120000 to 60000 for better performance
            "maxAge": 172800000,
        }
        data = self.client.post("/scrape", payload)
        scraped = data.get("data", data)
        extracted = scraped.get("json") or {}
        if isinstance(extracted, list):
            extracted = extracted[0] if extracted else {}
        markdown = scraped.get("markdown", "")
        metadata = scraped.get("metadata", {})

        record = dict(extracted) if isinstance(extracted, dict) else {}
        record["source_url"] = record.get("source_url") or metadata.get("sourceURL") or url
        record["application_link"] = record.get("application_link") or record["source_url"]
        record["budget"] = record.get("budget") or record.get("cost", "")
        record["program_type"] = record.get("program_type") or record.get("modality", "")
        record["raw_text_snippet"] = markdown[:400]
        record["source"] = "firecrawl"
        
        # Cache the result persistently
        self.cache[url] = record
        self._save_cache()
        return record


class SnapshotTool:
    """Tool: load bundled records when live Firecrawl is disabled."""

    def run(self, limit: int | None = None) -> list[dict[str, Any]]:
        records = json.loads(Path("data/programs.json").read_text(encoding="utf-8"))
        return records[:limit] if limit else records


class VerificationTool:
    """Tool: verify records and apply user-location constraints."""

    def run(self, records: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
        verified = [verify_record(dict(record), sample_grade=int(profile.get("grade", 11))) for record in records]
        return [record for record in verified if record_matches_location(record, profile)]


class MatchingTool:
    """Tool: rank verified records for the student profile."""

    def run(self, records: list[dict[str, Any]], profile: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
        programs = [Program.from_dict(record) for record in records]
        return rank_programs(programs, profile_to_student(profile), limit=limit)


class StorageTool:
    """Tool: persist verified program output to JSON, CSV, and SQLite."""

    def run(self, records: list[dict[str, Any]]) -> None:
        DATA_DIR.mkdir(exist_ok=True)
        # Remove budget from JSON output
        records_for_json = [{k: v for k, v in record.items() if k != "budget"} for record in records]
        FIRECRAWL_PROGRAMS_JSON_PATH.write_text(json.dumps(records_for_json, indent=2), encoding="utf-8")

        with FIRECRAWL_PROGRAMS_CSV_PATH.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for record in records:
                row = dict(record)
                subjects = row.get("subject_areas", [])
                if isinstance(subjects, list):
                    subjects_text = "; ".join(subjects)
                else:
                    subjects_text = str(subjects)
                row["program_type"] = row.get("program_type") or row.get("modality", "")
                row["subjects"] = subjects_text
                row["subject_areas"] = subjects_text
                writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})

        save_verified_records(records)
