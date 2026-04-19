from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from discover import DISCOVERED_URLS_PATH, discover_program_urls, polite_get
from schema import Program
from verify import verify_program, verify_record

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


DATA_DIR = Path("data")
PROGRAMS_JSON_PATH = DATA_DIR / "programs.json"
PROGRAMS_CSV_PATH = DATA_DIR / "programs.csv"


PROGRAM_HINTS = {
    "stanford-pre-collegiate-summer-institutes": {
        "program_name": "Stanford Pre-Collegiate Summer Institutes",
        "provider": "Stanford Pre-Collegiate Studies",
        "subject_areas": ["computer science", "engineering", "mathematics", "science", "humanities", "business"],
        "modality": "online",
        "location": "Online",
        "application_link": "https://summerinstitutes.spcs.stanford.edu/admissions",
    },
    "university-level-online-math-physics": {
        "program_name": "Stanford Pre-Collegiate University-Level Online Math & Physics",
        "provider": "Stanford Pre-Collegiate Studies",
        "subject_areas": ["mathematics", "physics", "science"],
        "modality": "online",
        "location": "Online",
        "application_link": "https://ulo.stanford.edu/admissions-ulo",
    },
    "summer-session.html": {
        "program_name": "Carnegie Mellon Pre-College Summer Session",
        "provider": "Carnegie Mellon University",
        "subject_areas": ["computer science", "engineering", "science", "humanities", "social science"],
        "modality": "in_person",
        "location": "Carnegie Mellon University, Pittsburgh, PA",
        "application_link": "https://www.cmu.edu/pre-college/admission/",
    },
    "computer-science-scholars.html": {
        "program_name": "Carnegie Mellon CS Scholars",
        "provider": "Carnegie Mellon University",
        "subject_areas": ["computer science", "mathematics", "college preparation"],
        "modality": "in_person",
        "location": "Carnegie Mellon University, Pittsburgh, PA",
        "application_link": "https://www.cmu.edu/pre-college/admission/",
    },
    "bwsi.mit.edu": {
        "program_name": "MIT Beaver Works Summer Institute",
        "provider": "MIT Beaver Works Summer Institute",
        "subject_areas": ["engineering", "computer science", "robotics", "AI", "autonomous systems"],
        "modality": "hybrid",
        "location": "Online prerequisites; July program through MIT Beaver Works",
        "application_link": "https://bwsi.mit.edu/apply-now/",
    },
    "girlswhocode.com/programs/pathways": {
        "program_name": "Girls Who Code Pathways",
        "provider": "Girls Who Code",
        "subject_areas": ["computer science", "AI", "data science", "cybersecurity", "web development", "game design"],
        "modality": "online",
        "location": "Virtual",
        "application_link": "https://girlswhocode.com/pathwaysapply",
    },
    "summer-computer-science-academy": {
        "program_name": "Berkeley Pre-College Scholars: Computer Science Academy",
        "provider": "UC Berkeley Summer Sessions",
        "subject_areas": ["computer science", "AI"],
        "modality": "in_person",
        "location": "University of California, Berkeley, CA",
        "application_link": "https://precollege.berkeley.edu/summer-computer-science-academy",
    },
    "programs/arise": {
        "program_name": "NYU ARISE",
        "provider": "NYU Tandon School of Engineering",
        "subject_areas": ["engineering", "computer science", "STEM research", "life sciences"],
        "modality": "hybrid",
        "location": "NYU Tandon School of Engineering, Brooklyn, NY",
        "application_link": "https://k12stem.engineering.nyu.edu/programs/arise",
    },
}


def fetch_page(url: str) -> tuple[str, str]:
    logger.info(f"Fetching page content from: {url}")
    # Refresh mode uses the shared polite fetcher so all network access follows
    # the same robots.txt, user-agent, and jitter rules.
    response = polite_get(url)
    logger.info(f"Successfully fetched {len(response.text)} characters from {url}")
    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)
    return response.text, re.sub(r"\s+", " ", text).strip()


def _hint_for_url(url: str) -> dict:
    for key, hint in PROGRAM_HINTS.items():
        if key in url:
            return hint
    return {}


def _first_match(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip(" .:-")
    return ""


def _description(soup: BeautifulSoup, page_text: str) -> str:
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    for paragraph in soup.find_all("p"):
        text = paragraph.get_text(" ", strip=True)
        if len(text) > 100:
            return text[:420].strip()
    return page_text[:300].strip()


def _infer_modality(text: str, hint: str = "") -> str:
    lowered = text.lower()
    if hint:
        return hint
    if "hybrid" in lowered or ("remote" in lowered and "campus" in lowered):
        return "hybrid"
    if "online" in lowered or "virtual" in lowered:
        return "online"
    if "residential" in lowered or "in-person" in lowered or "campus" in lowered:
        return "in_person"
    return "unknown"


def _extract_cost(text: str) -> str:
    free = re.search(r"(no cost|free|fully funded|100% free|tuition-free)", text, flags=re.IGNORECASE)
    money = re.search(r"(\$[0-9][0-9,]*(?:\s*(?:per course|program fee|tuition|residential|commuter|application fee)?)?)", text)
    if free and money:
        return f"{free.group(1)}; {money.group(1)}"
    if free:
        return free.group(1)
    if money:
        return money.group(1)
    return ""


def extract_program(url: str) -> Program:
    logger.info(f"Extracting program data from URL: {url}")
    html, page_text = fetch_page(url)
    soup = BeautifulSoup(html, "html.parser")
    hint = _hint_for_url(url)

    title = soup.find(["h1", "title"])
    program_name = hint.get("program_name") or (title.get_text(" ", strip=True) if title else url)

    program = Program(
        program_name=program_name,
        provider=hint.get("provider", ""),
        source_url=url,
        short_description=_description(soup, page_text),
        subject_areas=hint.get("subject_areas", []),
        modality=_infer_modality(page_text, hint.get("modality", "")),
        location=hint.get("location", _first_match([r"Location\s+(.{1,120})"], page_text)),
        grades_or_age_eligibility=_first_match(
            [
                r"Grade level\(s\)\s+([0-9\-]+)",
                r"grades?\s+([0-9]{1,2}\s*(?:-|and|or|to)\s*[0-9]{1,2})",
                r"(?:students|applicants).{0,80}(?:grade|age).{0,160}",
            ],
            page_text,
        ),
        eligibility_requirements=_first_match(
            [
                r"Eligibility Requirements\s+(.{40,700}?)(?:Selection Criteria|Program Schedule|Questions|Testimonials|$)",
                r"Eligibility\s+(.{40,700}?)(?:Refund Policy|Important Dates|High School Students|$)",
                r"Who Can Apply\s+(.{40,500}?)(?:What to Expect|$)",
            ],
            page_text,
        ),
        application_deadline=_first_match(
            [
                r"Application Deadline(?:s)?\s+(.{1,120})",
                r"Application closes:\s+(.{1,80})",
                r"deadline.{0,30}((?:January|February|March|April|May)\s+[0-9]{1,2},?\s+2026)",
                r"Apply by\s+(.{1,60})",
            ],
            page_text,
        ),
        budget=_extract_cost(page_text),
        program_dates=_first_match(
            [
                r"(?:Program|Course|Session) Dates?\s+(.{1,180})",
                r"Program Session:\s+(.{1,80})",
                r"Program start:\s+(.{1,80}?Program end:\s+.{1,80})",
                r"(June\s+[0-9]{1,2},?\s+2026\s*(?:-|to)\s*(?:July|August)\s+[0-9]{1,2},?\s+2026)",
            ],
            page_text,
        ),
        duration="",
        cost=_extract_cost(page_text),
        application_link=hint.get("application_link", ""),
    )
    program = verify_program(program, page_text)
    return Program.from_dict(verify_record(program.to_dict(), page_text=page_text))


def save_programs(programs: list[Program]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    PROGRAMS_JSON_PATH.write_text(
        json.dumps([program.to_dict() for program in programs], indent=2),
        encoding="utf-8",
    )

    import csv

    with PROGRAMS_CSV_PATH.open("w", newline="", encoding="utf-8") as csv_file:
        fieldnames = [
            "program_name",
            "provider",
            "source_url",
            "subjects",
            "subject_areas",
            "modality",
            "location",
            "grades_or_age_eligibility",
            "eligibility_requirements",
            "application_deadline",
            "program_dates",
            "duration",
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
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for program in programs:
            row = program.to_dict()
            row["subject_areas"] = "; ".join(program.subject_areas)
            row["subjects"] = row["subject_areas"]
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def run_extraction(urls: list[str] | None = None) -> list[Program]:
    logger.info("Starting program extraction process")
    if urls is None:
        if not DISCOVERED_URLS_PATH.exists():
            urls = discover_program_urls()
        else:
            discovered = json.loads(DISCOVERED_URLS_PATH.read_text(encoding="utf-8"))
            if isinstance(discovered, dict):
                urls = [item["url"] for item in discovered.get("results", []) if item.get("url")]
            else:
                urls = discovered
    logger.info(f"Extracting programs from {len(urls)} URLs")
    programs = [extract_program(url) for url in urls]
    logger.info(f"Successfully extracted {len(programs)} program records")
    save_programs(programs)
    logger.info(f"Saved extracted programs to {PROGRAMS_JSON_PATH}")
    return programs


if __name__ == "__main__":
    programs = run_extraction()
    print(f"Extracted {len(programs)} programs to {PROGRAMS_JSON_PATH}")
