"""Run database seed scripts idempotently (roles, admin, branches, exam patterns, syllabi, formulas)."""

from app import create_app
from scripts.seed_admin import seed_admin
from scripts.seed_branches import seed_branches
from scripts.seed_exam_patterns import seed_exam_patterns
from scripts.seed_formulas import seed_formulas
from scripts.seed_syllabus import seed_syllabus


def run_all_seeds() -> dict:
    """Seed roles, admin, branches, exam patterns, 5-branch syllabi, and formula library."""
    seed_admin()
    branches = seed_branches()
    patterns = seed_exam_patterns()
    versions = seed_syllabus()
    formulas = seed_formulas()
    return {
        "branches": list(branches.keys()),
        "patterns_created": patterns,
        "syllabus_versions_created": versions,
        "formulas_created": formulas,
    }


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        summary = run_all_seeds()
        print("Database seed complete:", summary)
