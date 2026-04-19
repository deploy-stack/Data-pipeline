from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Any

from dateutil import parser as date_parser

from schema import FieldVerification, Program, REQUIRED_FIELDS

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


KEY_FIELDS = [
    "grades_or_age_eligibility",
    "eligibility_requirements",
    "application_deadline",
    "modality",
    "location",
    "cost",
]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9$,.:-]+", value.lower()) if len(token) > 2]


def _snippet(page_text: str, value: str) -> str:
    normalized_page = re.sub(r"\s+", " ", page_text or "")
    tokens = _tokens(value)
    for token in tokens:
        index = normalized_page.lower().find(token.strip(".,"))
        if index >= 0:
            start = max(index - 70, 0)
            end = min(index + 170, len(normalized_page))
            return normalized_page[start:end].strip()
    return ""


def verify_value(value: str, page_text: str, *, required_keywords: list[str] | None = None) -> FieldVerification:
    if not value:
        return FieldVerification(False, 0.0, "No extracted value.")

    normalized_page = normalize_text(page_text)
    normalized_value = normalize_text(value)
    required_keywords = required_keywords or []

    exact = normalized_value and normalized_value in normalized_page
    token_hits = sum(1 for token in _tokens(value) if token.strip(".,") in normalized_page)
    token_total = max(len(_tokens(value)), 1)
    keyword_hits = sum(1 for word in required_keywords if word.lower() in normalized_page)

    if exact:
        confidence = 0.95
    else:
        confidence = min(0.85, 0.25 + (token_hits / token_total) * 0.55 + keyword_hits * 0.05)

    verified = exact or confidence >= 0.65
    return FieldVerification(verified, round(confidence, 2), _snippet(page_text, value))


def verify_program(program: Program, page_text: str) -> Program:
    checks = {
        "grades_or_age_eligibility": ["grade", "age", "eligible"],
        "eligibility_requirements": ["eligible", "eligibility", "requirements"],
        "application_deadline": ["deadline", "application"],
        "modality": ["online", "virtual", "in-person", "residential", "commuter"],
        "location": ["location", "campus", "online", "virtual"],
        "cost": ["cost", "tuition", "fee", "free", "$"],
    }

    program.verification = {
        field: verify_value(str(getattr(program, field)), page_text, required_keywords=keywords)
        for field, keywords in checks.items()
    }

    present = 0
    for field in REQUIRED_FIELDS:
        value = getattr(program, field)
        if isinstance(value, list):
            present += bool(value)
        else:
            present += bool(str(value).strip())

    key_verified = sum(1 for result in program.verification.values() if result.verified)
    completeness = (present / len(REQUIRED_FIELDS)) * 0.75 + (key_verified / len(KEY_FIELDS)) * 0.25
    program.completeness_score = round(completeness, 2)
    return program


def parse_deadline(text: str) -> str | None:
    """Return an ISO date when deadline text contains a parseable date."""
    if not text:
        return None
    try:
        parsed = date_parser.parse(
            text,
            fuzzy=True,
            tzinfos={"EST": -18000, "PST": -28800, "PT": -28800},
        )
    except (ValueError, OverflowError):
        return None
    return parsed.date().isoformat()


def contains_high_school(text: str) -> bool:
    """Detect high-school eligibility language or common grade references."""
    lowered = normalize_text(text)
    if "high school" in lowered or "secondary school" in lowered:
        return True
    grade_patterns = [
        r"\b(?:8|9|10|11|12)(?:th|st|nd|rd)?\s*grade\b",
        r"\bgrades?\s*(?:8|9|10|11|12)(?:\s*[-toandor]+\s*(?:8|9|10|11|12))?\b",
        r"\b(?:freshman|sophomore|junior|senior)s?\b",
        r"\brising\s+(?:junior|senior|sophomore|freshman)s?\b",
    ]
    return any(re.search(pattern, lowered) for pattern in grade_patterns)


def numeric_cost(text: str) -> float | None:
    """Extract the first numeric USD amount when cost text includes dollars."""
    if not text:
        return None
    match = re.search(r"\$([0-9][0-9,]*(?:\.[0-9]{2})?)", text)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _record_text(record: dict[str, Any]) -> str:
    parts = []
    for value in record.values():
        if isinstance(value, list):
            parts.append(" ".join(str(item) for item in value))
        elif isinstance(value, (str, int, float)):
            parts.append(str(value))
    return " ".join(parts)


def verify_record(
    record: dict[str, Any],
    sample_grade: int | None = None,
    page_text: str | None = None,
) -> dict[str, Any]:
    """Enrich one extracted record with lightweight verification metadata."""
    program_name = record.get("program_name", "Unknown Program")
    logger.info(f"Verifying record for program: {program_name}")
    text = page_text or _record_text(record)
    deadline_iso = parse_deadline(str(record.get("application_deadline", "")))
    eligibility_text = " ".join(
        [
            str(record.get("grades_or_age_eligibility", "")),
            str(record.get("eligibility_requirements", "")),
        ]
    )
    cost_text = str(record.get("cost", ""))
    record["budget"] = record.get("budget") or cost_text
    record["program_type"] = record.get("program_type") or record.get("modality", "")
    cost_value = numeric_cost(cost_text)
    has_free_cost = any(word in cost_text.lower() for word in ["free", "no cost", "fully funded"])

    if deadline_iso:
        record["application_deadline"] = deadline_iso

    record["deadline_verified"] = deadline_iso is not None
    record["eligibility_verified"] = contains_high_school(eligibility_text)
    if sample_grade is not None:
        record["eligibility_verified"] = record["eligibility_verified"] and str(sample_grade) in eligibility_text
    record["cost_numeric"] = cost_value
    record["cost_verified"] = cost_value is not None or has_free_cost
    record["raw_text_snippet"] = (record.get("raw_text_snippet") or text[:400]).strip()
    record["source"] = record.get("source") or "official_website"

    score = 0.0
    score += 0.3 if record["deadline_verified"] else 0.0
    score += 0.3 if record["eligibility_verified"] else 0.0
    score += 0.2 if record["raw_text_snippet"] else 0.0
    score += 0.1 if str(record.get("location", "")).strip() else 0.0
    score += 0.1 if record["cost_verified"] else 0.0
    record["confidence_score"] = round(score, 2)

    required = ["program_name", "source_url", "application_deadline", "eligibility_requirements"]
    present = sum(bool(str(record.get(field, "")).strip()) for field in required)
    record["completeness_score"] = round(present / len(required), 2)

    if record["confidence_score"] >= 0.8:
        record["extraction_confidence"] = "high"
    elif record["confidence_score"] >= 0.5:
        record["extraction_confidence"] = "medium"
    else:
        record["extraction_confidence"] = "low"

    logger.info(f"Verification completed for {program_name}: confidence={record['confidence_score']}, completeness={record['completeness_score']}")
    # Last checked is generated at verification time so the demo can discuss
    # freshness without needing a production scheduler.
    record["last_checked"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return record
