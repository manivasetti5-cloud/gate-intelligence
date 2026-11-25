"""Seed official GATE examination patterns per branch and examination year."""

from app.extensions import db
from app.models.syllabus import Branch, ExamPattern

SUPPORTED_YEARS = [2026, 2025, 2024]


def build_official_rules(branch_code: str, year: int) -> dict:
    """Return official GATE marking and section distribution rules."""
    return {
        "exam_code": branch_code,
        "exam_year": year,
        "sections": [
            {
                "name": "General Aptitude",
                "total_questions": 10,
                "total_marks": 15,
                "one_mark_count": 5,
                "two_mark_count": 5,
            },
            {
                "name": "Core Subject & Engineering Mathematics",
                "total_questions": 55,
                "total_marks": 85,
                "one_mark_count": 25,
                "two_mark_count": 30,
            },
        ],
        "question_types_supported": ["MCQ", "MSQ", "NAT"],
        "marking_scheme": {
            "MCQ_1": {"correct": 1.0, "incorrect": -1.0 / 3.0, "unattempted": 0.0},
            "MCQ_2": {"correct": 2.0, "incorrect": -2.0 / 3.0, "unattempted": 0.0},
            "MSQ_1": {"correct": 1.0, "incorrect": 0.0, "partial": False, "unattempted": 0.0},
            "MSQ_2": {"correct": 2.0, "incorrect": 0.0, "partial": False, "unattempted": 0.0},
            "NAT_1": {"correct": 1.0, "incorrect": 0.0, "unattempted": 0.0},
            "NAT_2": {"correct": 2.0, "incorrect": 0.0, "unattempted": 0.0},
        },
        "virtual_calculator_allowed": True,
        "pattern_notes": "Official GATE 65-question, 100-mark, 180-minute CBT pattern.",
    }


def seed_exam_patterns() -> int:
    """Idempotently seed official GATE exam patterns for all active branches and years."""
    created = 0
    branches = Branch.query.all()
    for branch in branches:
        for year in SUPPORTED_YEARS:
            # DA was introduced starting GATE 2024
            if branch.code == "DA" and year < 2024:
                continue
            existing = ExamPattern.query.filter_by(branch_id=branch.id, exam_year=year).first()
            if not existing:
                pattern = ExamPattern(
                    branch_id=branch.id,
                    exam_year=year,
                    duration_minutes=180,
                    total_marks=100,
                    total_questions=65,
                    ga_marks=15,
                    technical_marks=85,
                    rules_json=build_official_rules(branch.code, year),
                    is_active=True,
                )
                db.session.add(pattern)
                created += 1
    db.session.commit()
    return created


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        count = seed_exam_patterns()
        print(f"Seeded {count} exam patterns.")
