from __future__ import annotations

from pathlib import Path


def run_quality_checks(
    csv_path: str = "data/programs.csv",
    db_path: str = "data/demo.duckdb",
) -> dict:
    """Load the CSV into DuckDB and return tiny demo-quality metrics."""
    import duckdb

    csv_file = Path(csv_path)
    if not csv_file.exists():
        raise FileNotFoundError(f"Missing CSV: {csv_path}")

    Path(db_path).parent.mkdir(exist_ok=True)
    with duckdb.connect(db_path) as con:
        con.execute(
            "CREATE OR REPLACE TABLE programs AS SELECT * FROM read_csv_auto(?)",
            [str(csv_file)],
        )
        columns = {row[1] for row in con.execute("PRAGMA table_info('programs')").fetchall()}

        total = con.execute("SELECT COUNT(*) FROM programs").fetchone()[0]
        if "application_deadline" in columns:
            missing_deadlines = con.execute(
                """
                SELECT COUNT(*)
                FROM programs
                WHERE application_deadline IS NULL OR trim(application_deadline) = ''
                """
            ).fetchone()[0]
        else:
            missing_deadlines = total

        avg_confidence = 0.0
        if "confidence_score" in columns:
            avg_confidence = con.execute(
                "SELECT COALESCE(AVG(try_cast(confidence_score AS DOUBLE)), 0) FROM programs"
            ).fetchone()[0]

    return {
        "db_path": db_path,
        "total_programs": int(total),
        "missing_deadlines": int(missing_deadlines),
        "missing_deadlines_count": int(missing_deadlines),
        "avg_confidence": round(float(avg_confidence or 0.0), 2),
    }


if __name__ == "__main__":
    print(run_quality_checks())
