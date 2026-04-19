from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


DB_PATH = Path("data/programs.sqlite")
DB_FIELDS = [
    "eligibility_requirements",
    "application_deadline",
    "program_type",
    "location",
    "provider",
    "duration",
    "program_name",
]


def save_verified_records(records: list[dict[str, Any]], db_path: str | Path = DB_PATH) -> None:
    """Persist verified structured program records into a tiny SQLite database."""
    db_path = Path(db_path)
    db_path.parent.mkdir(exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE IF EXISTS verified_programs")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS verified_programs (
                eligibility_requirements TEXT,
                application_deadline TEXT,
                program_type TEXT,
                location TEXT,
                provider TEXT,
                duration TEXT,
                program_name TEXT
            )
            """
        )
        conn.execute("DELETE FROM verified_programs")
        for record in records:
            conn.execute(
                """
                INSERT INTO verified_programs (
                    eligibility_requirements,
                    application_deadline,
                    program_type,
                    location,
                    provider,
                    duration,
                    program_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("eligibility_requirements", ""),
                    record.get("application_deadline", ""),
                    record.get("program_type") or record.get("modality", ""),
                    record.get("location", ""),
                    record.get("provider", ""),
                    record.get("duration", ""),
                    record.get("program_name", ""),
                ),
            )
        conn.commit()


if __name__ == "__main__":
    print(f"SQLite database path: {DB_PATH}")
