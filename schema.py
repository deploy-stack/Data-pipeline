from __future__ import annotations

from dataclasses import asdict, dataclass, field
import logging
from typing import Any, Optional

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


REQUIRED_FIELDS = [
    "eligibility_requirements",
    "application_deadline",
    "budget",
    "program_type",
    "location",
    "provider",
    "duration",
    "program_name",
    "source_url",
    "short_description",
    "subject_areas",
    "modality",
    "grades_or_age_eligibility",
    "program_dates",
    "cost",
    "application_link",
]

PROVENANCE_FIELDS = [
    "last_checked",
    "source",
    "raw_text_snippet",
    "deadline_verified",
    "eligibility_verified",
    "cost_verified",
    "extraction_confidence",
    "confidence_score",
    "completeness_score",
    "cost_numeric",
]


@dataclass
class FieldVerification:
    verified: bool
    confidence: float
    evidence: str = ""


@dataclass
class ProgramRecord:
    """Simple standalone record shape for demos or exports.

    The existing Program class below keeps matcher compatibility; this record
    mirrors the compact schema shown in the interview notes.
    """

    eligibility_requirements: Optional[str]
    application_deadline: Optional[str]
    budget: Optional[str]
    program_type: Optional[str]
    location: Optional[str]
    provider: Optional[str]
    duration: Optional[str]
    program_name: str
    source_url: str
    short_description: Optional[str] = None
    subject_areas: Optional[list[str]] = None
    modality: Optional[str] = None
    grades_or_age_eligibility: Optional[str] = None
    program_dates: Optional[str] = None
    duration_weeks: Optional[int] = None
    cost: Optional[str] = None
    application_link: Optional[str] = None
    last_checked: Optional[str] = None
    source: Optional[str] = None
    raw_text_snippet: Optional[str] = None
    deadline_verified: bool = False
    eligibility_verified: bool = False
    cost_verified: bool = False
    extraction_confidence: Optional[str] = None
    confidence_score: float = 0.0
    completeness_score: float = 0.0


@dataclass
class Program:
    """Structured program record used by the demo pipeline.

    New provenance and verification fields:
    last_checked: UTC ISO datetime for the latest verification pass.
    source: Human-readable source label, usually "official_website".
    raw_text_snippet: Short page-text excerpt used for traceable verification.
    deadline_verified: True when a deadline could be parsed from explicit text.
    eligibility_verified: True when high-school or grade eligibility is detected.
    cost_verified: True when cost text or a numeric USD amount is present.
    extraction_confidence: Label derived from confidence_score: high, medium, or low.
    confidence_score: Weighted verification confidence from 0.0 to 1.0.
    completeness_score: Required-field completeness from 0.0 to 1.0.
    cost_numeric: Parsed numeric USD amount when available.
    """

    program_name: str
    provider: str
    source_url: str
    short_description: str
    subject_areas: list[str]
    modality: str
    location: str
    grades_or_age_eligibility: str
    eligibility_requirements: str
    application_deadline: str
    budget: str
    program_type: str
    location: str
    program_dates: str
    duration: str
    cost: str
    application_link: str = ""
    last_checked: str = ""
    source: str = "official_website"
    raw_text_snippet: str = ""
    deadline_verified: bool = False
    eligibility_verified: bool = False
    cost_verified: bool = False
    extraction_confidence: str = "low"
    confidence_score: float = 0.0
    cost_numeric: float | None = None
    verification: dict[str, FieldVerification] = field(default_factory=dict)
    completeness_score: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Program":
        program_name = data.get("program_name", "Unknown Program")
        logger.info(f"Creating Program schema object for: {program_name}")
        verification = {
            name: FieldVerification(**result)
            for name, result in data.get("verification", {}).items()
        }
        clean = {name: data.get(name, "") for name in REQUIRED_FIELDS}
        for name, value in list(clean.items()):
            if value is None:
                clean[name] = [] if name == "subject_areas" else ""
        if not clean["subject_areas"] and data.get("subjects"):
            clean["subject_areas"] = data.get("subjects", "")
        if not clean["budget"]:
            clean["budget"] = data.get("cost", "")
        if not clean["program_type"]:
            clean["program_type"] = data.get("modality", "")
        if isinstance(clean["subject_areas"], str):
            separator = ";" if ";" in clean["subject_areas"] else ","
            clean["subject_areas"] = [
                subject.strip()
                for subject in clean["subject_areas"].split(separator)
                if subject.strip()
            ]
        for name in PROVENANCE_FIELDS:
            if name in {"deadline_verified", "eligibility_verified", "cost_verified"}:
                clean[name] = bool(data.get(name, False))
            elif name in {"confidence_score", "completeness_score"}:
                clean[name] = float(data.get(name, 0.0) or 0.0)
            else:
                clean[name] = data.get(name, None if name == "cost_numeric" else "")
        logger.info(f"Program schema created: {program_name} with {len(clean['subject_areas'])} subject areas")
        return cls(
            **clean,
            verification=verification,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StudentProfile:
    grade: int
    interests: list[str]
    preferred_modality: str
    budget_max: int
