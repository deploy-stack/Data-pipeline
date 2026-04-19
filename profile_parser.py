from __future__ import annotations

import re
from typing import Any


INTEREST_KEYWORDS = {
    "computer science": ["computer science", "cs", "coding", "programming", "software"],
    "AI": ["ai", "artificial intelligence", "machine learning"],
    "engineering": ["engineering", "robotics"],
    "math": ["math", "mathematics"],
    "biology": ["biology", "bio", "life science", "life sciences"],
    "business": ["business", "entrepreneurship", "startup"],
}


def parse_user_profile_text(text: str, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    """Convert a natural-language student request into the same profile dict as the form."""
    defaults = defaults or {}
    lowered = text.lower()

    grade = defaults.get("grade", 11)
    grade_match = re.search(r"\bgrade\s*(8|9|10|11|12)\b|\b(8|9|10|11|12)(?:th|st|nd|rd)\s*grade\b", lowered)
    if grade_match:
        grade = int(next(group for group in grade_match.groups() if group))

    modality = defaults.get("preferred_modality", "online")
    if "hybrid" in lowered:
        modality = "hybrid"
    elif "in person" in lowered or "in-person" in lowered or "on campus" in lowered:
        modality = "in_person"
    elif "online" in lowered or "virtual" in lowered:
        modality = "online"

    budget = defaults.get("budget_max", 4000)
    budget_match = re.search(r"\$\s*([0-9][0-9,]*)", lowered)
    if not budget_match:
        budget_match = re.search(r"(?:budget|max|maximum|under|below|less than)\s+\$?\s*([0-9][0-9,]*)", lowered)
    if budget_match:
        budget = int(budget_match.group(1).replace(",", ""))

    include_online = any(word in lowered for word in ["online", "virtual", "remote"])
    radius = int(defaults.get("radius_miles", 50))
    radius_match = re.search(r"(?:within|inside|under)\s+([0-9]{1,3})\s*miles?", lowered)
    if radius_match:
        radius = int(radius_match.group(1))

    location = defaults.get("location_preference", "")
    location_match = re.search(r"(?:near|around)\s+([a-zA-Z .,-]+?)(?:\s+within|\s+under|,|\.|$)", text, re.I)
    if not location_match:
        location_match = re.search(r"(?:located in|programs in|courses in)\s+([a-zA-Z .,-]+?)(?:\s+within|\s+under|,|\.|$)", text, re.I)
    if location_match:
        location = location_match.group(1).strip()

    interests = []
    for canonical, aliases in INTEREST_KEYWORDS.items():
        if any(alias in lowered for alias in aliases):
            interests.append(canonical)

    return {
        "grade": int(grade),
        "interests": interests or list(defaults.get("interests", [])),
        "preferred_modality": modality,
        "budget_max": int(budget),
        "location_preference": location,
        "radius_miles": radius,
        "include_online": include_online or bool(defaults.get("include_online", True)),
    }
