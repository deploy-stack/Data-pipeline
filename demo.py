from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Any

from discover import discover_program_urls
from match import rank_programs
from schema import Program, StudentProfile
from verify import verify_record
from program_database import save_verified_records

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


DATA_DIR = Path("data")
PROGRAMS_JSON_PATH = DATA_DIR / "programs.json"
PROGRAMS_CSV_PATH = DATA_DIR / "programs.csv"


CSV_FIELDS = [
    "eligibility_requirements",
    "application_deadline",
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


def load_records(limit: int | None = None) -> list[dict[str, Any]]:
    if not PROGRAMS_JSON_PATH.exists():
        raise FileNotFoundError(f"{PROGRAMS_JSON_PATH} is missing.")
    records = json.loads(PROGRAMS_JSON_PATH.read_text(encoding="utf-8"))
    return records[:limit] if limit else records


def save_records(records: list[dict[str, Any]]) -> None:
    """Persist the verified offline snapshot for the Streamlit app and CLI."""
    DATA_DIR.mkdir(exist_ok=True)
    # Remove budget from JSON output
    records_for_json = [{k: v for k, v in record.items() if k != "budget"} for record in records]
    PROGRAMS_JSON_PATH.write_text(json.dumps(records_for_json, indent=2), encoding="utf-8")

    with PROGRAMS_CSV_PATH.open("w", newline="", encoding="utf-8") as csv_file:
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


def verify_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    verified = []
    for record in records:
        # Offline verification uses the record text as a snapshot stand-in; live
        # refresh passes page text from extract.py before records are saved.
        verified.append(verify_record(dict(record)))
    return verified


def print_quality_summary() -> None:
    print("\nDATA QUALITY SUMMARY")
    print("=" * 72)
    try:
        from storage_duckdb import run_quality_checks

        checks = run_quality_checks(str(PROGRAMS_CSV_PATH))
    except Exception as exc:
        print(f"Quality checks unavailable: {exc}")
        return

    print(f"Total programs: {checks['total_programs']}")
    print(f"Missing deadlines: {checks['missing_deadlines_count']}")
    print(f"Average confidence: {checks['avg_confidence']}")


def print_final_metrics(records: list[dict[str, Any]], sources_explored: int | None = None) -> None:
    required_attrs = [
        "eligibility_requirements",
        "application_deadline",
        "budget",
        "provider",
        "duration",
        "program_name",
    ]
    data_points = sum(1 for record in records for field in required_attrs if record.get(field))
    verified = sum(1 for record in records if record.get("eligibility_verified") or record.get("deadline_verified"))
    print("\nFINAL OUTPUT METRICS")
    print("=" * 72)
    print(f"Data sources explored: {sources_explored if sources_explored is not None else len(records)}")
    print(f"Data points extracted: {data_points}")
    print(f"Records verified against user details: {verified}")


def print_matches(programs: list[Program]) -> None:
    student = StudentProfile(
        grade=11,
        interests=["computer science", "AI", "engineering"],
        preferred_modality="online",
        budget_max=4000,
    )

    print("\nMATCHING DEMO")
    print("=" * 72)
    print("Sample student: grade 11, CS/AI/engineering, online preferred, budget $4,000")

    for index, item in enumerate(rank_programs(programs, student, limit=5), start=1):
        program = item["program"]
        matched = ", ".join(item.get("matched_interests", [])) or "none"
        unmatched = ", ".join(item.get("unmatched_interests", [])) or "none"
        print(f"\n{index}. {program.program_name} - score {item['score']}")
        print(f"   {program.provider} | {program.modality} | {program.cost or 'cost unknown'}")
        print(f"   Matched interests: {matched}; unmatched: {unmatched}")
        print(f"   Why: {'; '.join(item['reasons'])}")
        print(f"   Source: {program.source_url}")


def main() -> None:
    logger.info("Starting Vantion pre-college program matching demo")
    parser = argparse.ArgumentParser(description="Vantion pre-college program matching demo")
    parser.add_argument("--refresh", action="store_true", help="Fetch official pages and rebuild data files.")
    parser.add_argument("--agentic", action="store_true", help="Run the profile-driven Firecrawl agent pipeline.")
    parser.add_argument("--limit", type=int, default=None, help="Limit records processed for a quick demo run.")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for processing large numbers of sources.")
    args = parser.parse_args()

    if args.agentic:
        logger.info("Running agentic pipeline mode with profile-driven Firecrawl agent")
        from orchestrator_agent import run_agentic_pipeline

        profile = {
            "grade": 11,
            "interests": ["computer science", "AI", "engineering"],
            "preferred_modality": "online",
            "budget_max": 4000,
        }
        logger.info(f"Using student profile: {profile}")
        result = run_agentic_pipeline(
            profile,
            use_firecrawl=True,
            source_limit=args.limit or 5,
            extraction_limit=args.limit or 5,
            batch_size=args.batch_size,
        )
        for message in result.messages:
            logger.info(f"Agent message: {message}")
        verified_records = result.records
        logger.info(f"Agentic pipeline completed with {len(verified_records)} records")
        programs = [Program.from_dict(record) for record in verified_records]
        print_quality_summary()
        print_final_metrics(verified_records, result.metrics.get("sources_explored"))
        print_matches(programs)
        print(f"\nAgentic data written to data/firecrawl_programs.json and data/firecrawl_programs.csv")
        return

    if args.refresh:
        logger.info("Running refresh mode: fetching official pages and rebuilding data files")
        from extract import run_extraction

        urls = discover_program_urls()
        if args.limit:
            urls = urls[: args.limit]
        logger.info(f"Discovered {len(urls)} program URLs to process")
        print(f"Refreshing {len(urls)} official program pages...")
        programs = run_extraction(urls)
        records = [program.to_dict() for program in programs]
        logger.info(f"Extracted {len(records)} program records")
    else:
        logger.info("Loading pre-verified records from data/programs.json")
        records = load_records()

    logger.info(f"Starting verification of {len(records)} records")
    verified_records = verify_records(records)
    logger.info(f"Verification completed: {len(verified_records)} records verified")
    save_records(verified_records)
    logger.info(f"Saved verified data to {PROGRAMS_JSON_PATH} and {PROGRAMS_CSV_PATH}")
    displayed_records = verified_records[: args.limit] if args.limit else verified_records
    programs = [Program.from_dict(record) for record in displayed_records]
    logger.info(f"Generated {len(programs)} Program schema objects for matching")

    print_quality_summary()
    print_final_metrics(displayed_records)
    print_matches(programs)
    print(f"\nVerified data written to {PROGRAMS_JSON_PATH} and {PROGRAMS_CSV_PATH}")


if __name__ == "__main__":
    main()
