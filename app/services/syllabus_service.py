"""Syllabus hierarchy, version resolution, and exam pattern helpers."""

from sqlalchemy import desc
from sqlalchemy.orm import joinedload

from app.models.syllabus import (
    Branch,
    Chapter,
    Concept,
    ExamPattern,
    Subject,
    SyllabusVersion,
    Topic,
)


def get_active_branches() -> list[Branch]:
    """Return all active GATE branches ordered by code."""
    return Branch.query.filter_by(is_active=True).order_by(Branch.code.asc()).all()


def get_available_exam_years(branch_id: int | None = None) -> list[int]:
    """Return distinct exam years that have syllabus versions or exam patterns."""
    query = SyllabusVersion.query
    if branch_id:
        query = query.filter_by(branch_id=branch_id)
    years = sorted({sv.exam_year for sv in query.all()}, reverse=True)
    return years or [2026, 2025, 2024]


def resolve_syllabus_version(branch_id: int, exam_year: int | None = None) -> SyllabusVersion | None:
    """Resolve the active syllabus version for a branch and year, falling back to latest active."""
    if exam_year is not None:
        exact = (
            SyllabusVersion.query.filter_by(
                branch_id=branch_id, exam_year=exam_year, status="active"
            )
            .order_by(desc(SyllabusVersion.effective_date))
            .first()
        )
        if exact:
            return exact

    return (
        SyllabusVersion.query.filter_by(branch_id=branch_id, status="active")
        .order_by(desc(SyllabusVersion.exam_year), desc(SyllabusVersion.effective_date))
        .first()
    )


def get_syllabus_tree(syllabus_version_id: int) -> list[Subject]:
    """Load the full Subject -> Chapter -> Topic -> Concept hierarchy for a syllabus version."""
    return (
        Subject.query.filter_by(syllabus_version_id=syllabus_version_id)
        .options(
            joinedload(Subject.chapters)
            .joinedload(Chapter.topics)
            .joinedload(Topic.concepts)
        )
        .order_by(Subject.display_order.asc(), Subject.name.asc())
        .all()
    )


def get_exam_pattern(branch_id: int, exam_year: int | None = None) -> ExamPattern | None:
    """Resolve the active ExamPattern for a branch and optional year."""
    if exam_year is not None:
        exact = ExamPattern.query.filter_by(
            branch_id=branch_id, exam_year=exam_year, is_active=True
        ).first()
        if exact:
            return exact

    return (
        ExamPattern.query.filter_by(branch_id=branch_id, is_active=True)
        .order_by(desc(ExamPattern.exam_year))
        .first()
    )


def count_syllabus_nodes(syllabus_version_id: int) -> dict[str, int]:
    """Return summary counts of subjects, chapters, topics, and concepts in a syllabus version."""
    subjects = Subject.query.filter_by(syllabus_version_id=syllabus_version_id).all()
    subject_ids = [s.id for s in subjects]
    if not subject_ids:
        return {"subjects": 0, "chapters": 0, "topics": 0, "concepts": 0}

    chapters = Chapter.query.filter(Chapter.subject_id.in_(subject_ids)).all()
    chapter_ids = [c.id for c in chapters]
    if not chapter_ids:
        return {"subjects": len(subjects), "chapters": 0, "topics": 0, "concepts": 0}

    topics = Topic.query.filter(Topic.chapter_id.in_(chapter_ids)).all()
    topic_ids = [t.id for t in topics]
    concepts_count = (
        Concept.query.filter(Concept.topic_id.in_(topic_ids)).count() if topic_ids else 0
    )
    return {
        "subjects": len(subjects),
        "chapters": len(chapters),
        "topics": len(topics),
        "concepts": concepts_count,
    }
