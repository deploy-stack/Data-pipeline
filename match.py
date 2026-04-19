from __future__ import annotations

import logging
import re

from schema import Program, StudentProfile

# Matching utilities for ranking programs against student profile preferences.
logger = logging.getLogger(__name__)


INTEREST_ALIASES = {
    "computer science": ["computer science", "computing", "coding", "programming", "software"],
    "AI": ["ai", "artificial intelligence", "machine learning", "data science", "autonomous systems"],
    "engineering": ["engineering", "robotics", "autonomous systems", "stem"],
    "math": ["math", "mathematics", "physics", "quantitative"],
    "biology": ["biology", "bioscience", "life sciences", "biomedical", "medicine"],
    "business": ["business", "entrepreneurship", "technology and business", "management"],
}


def _cost_amount(cost: str) -> int | None:
    if not cost:
        return None
    if any(word in cost.lower() for word in ["free", "no cost", "fully funded", "tuition-free"]):
        return 0
    match = re.search(r"\$([0-9][0-9,]*)", cost)
    return int(match.group(1).replace(",", "")) if match else None


def _grade_fits(student_grade: int, eligibility: str) -> bool:
    text = eligibility.lower()
    if not text:
        return False
    if f"{student_grade}" in text:
        return True
    if "9-12" in text or "9th-12th" in text or "high school" in text:
        return True
    if student_grade == 11 and any(phrase in text for phrase in ["junior", "rising senior", "10th and 11th", "11th grade"]):
        return True
    return False


def _program_subject_text(program: Program) -> str:
    parts = [
        " ".join(program.subject_areas),
        program.program_name,
        program.short_description,
    ]
    return " ".join(parts).lower()


def _interest_match_kind(interest: str, program: Program) -> str | None:
    subject_text = _program_subject_text(program)
    listed_subjects = [subject.lower() for subject in program.subject_areas]
    aliases = INTEREST_ALIASES.get(interest, [interest])

    if interest.lower() in listed_subjects:
        return "exact"

    for alias in aliases:
        alias = alias.lower()
        if any(alias == subject or alias in subject for subject in listed_subjects):
            return "exact"

    for alias in aliases:
        if alias.lower() in subject_text:
            return "close"

    return None


def analyze_program_match(program: Program, student: StudentProfile) -> dict:
    logger.info(f"Analyzing match for program: {program.program_name}")
    score = 0.0
    reasons: list[str] = []
    breakdown: dict[str, float] = {}

    matched_interests: list[str] = []
    exact_matches: list[str] = []
    close_matches: list[str] = []
    unmatched_interests: list[str] = []

    for interest in student.interests:
        match_kind = _interest_match_kind(interest, program)
        if match_kind == "exact":
            exact_matches.append(interest)
            matched_interests.append(interest)
        elif match_kind == "close":
            close_matches.append(interest)
            matched_interests.append(interest)
        else:
            unmatched_interests.append(interest)

    if student.interests:
        interest_score = len(exact_matches) * 35 + len(close_matches) * 25
        coverage_bonus = (len(matched_interests) / len(student.interests)) * 25
        interest_score += coverage_bonus

        if not matched_interests:
            interest_score -= 45
            reasons.append("no meaningful overlap with selected interests")
        else:
            reasons.append("matched selected interests: " + ", ".join(matched_interests))

        if unmatched_interests:
            interest_score -= len(unmatched_interests) * 12
            reasons.append("did not match: " + ", ".join(unmatched_interests))

        score += interest_score
        breakdown["interest relevance"] = round(interest_score, 1)
    else:
        breakdown["interest relevance"] = 0.0
        reasons.append("no interests selected")

    eligibility_blob = f"{program.grades_or_age_eligibility} {program.eligibility_requirements}"
    if _grade_fits(student.grade, eligibility_blob):
        score += 18
        breakdown["eligibility"] = 18
        reasons.append(f"eligibility appears compatible with grade {student.grade}")
    elif eligibility_blob:
        score += 5
        breakdown["eligibility"] = 5
        reasons.append("eligibility is present but may need counselor review")
    else:
        breakdown["eligibility"] = 0

    if program.modality == student.preferred_modality:
        score += 12
        breakdown["modality"] = 12
        reasons.append(f"preferred {student.preferred_modality} modality")
    elif program.modality == "hybrid" and student.preferred_modality == "online":
        score += 6
        breakdown["modality"] = 6
        reasons.append("hybrid option may still include online work")
    else:
        breakdown["modality"] = 0

    amount = _cost_amount(program.cost)
    if amount is None:
        score += 3
        breakdown["budget"] = 3
        reasons.append("cost needs follow-up")
    elif amount <= student.budget_max:
        score += 12
        breakdown["budget"] = 12
        reasons.append(f"cost appears within ${student.budget_max:,} budget")
    else:
        breakdown["budget"] = 0
        reasons.append(f"cost may exceed ${student.budget_max:,} budget")

    if program.application_deadline:
        score += 5
        breakdown["deadline"] = 5
        reasons.append("deadline is available for planning")
    else:
        breakdown["deadline"] = 0

    completeness_points = round(program.completeness_score * 3, 1)
    score += completeness_points
    breakdown["data completeness"] = completeness_points

    return {
        "score": round(max(score, 0), 1),
        "reasons": reasons,
        "matched_interests": matched_interests,
        "unmatched_interests": unmatched_interests,
        "exact_interest_matches": exact_matches,
        "close_interest_matches": close_matches,
        "score_breakdown": breakdown,
    }


def score_program(program: Program, student: StudentProfile) -> tuple[float, list[str]]:
    analysis = analyze_program_match(program, student)
    return analysis["score"], analysis["reasons"]


def rank_programs(programs: list[Program], student: StudentProfile, limit: int = 5) -> list[dict]:
    logger.info(f"Starting program matching for student profile: grade {student.grade}, interests {student.interests}, modality {student.preferred_modality}, budget ${student.budget_max}")
    ranked = []
    for program in programs:
        analysis = analyze_program_match(program, student)
        ranked.append({"program": program, **analysis})
    logger.info(f"Matching completed: ranked {len(ranked)} programs, returning top {limit}")
    return sorted(ranked, key=lambda item: item["score"], reverse=True)[:limit]
