"""Question bank creation, normalization, filtering, and provenance helpers."""

import hashlib
import re

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.question import (
    AnswerVerification,
    Question,
    QuestionOption,
    QuestionSource,
    QuestionTag,
)


def compute_normalized_hash(statement_md: str) -> str:
    """Compute SHA-256 hash of normalized whitespace/punctuation-folded statement."""
    cleaned = re.sub(r"\s+", " ", (statement_md or "").strip().lower())
    cleaned = re.sub(r"[^a-z0-9\s\+\-\*/=<>.,()]", "", cleaned)
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def default_negative_marks(question_type: str, marks: int) -> float:
    """Return official GATE negative marks for a question type and mark weight."""
    qtype = (question_type or "").upper()
    if qtype == "MCQ":
        return round(marks / 3.0, 4)
    return 0.0


def create_question_record(
    *,
    branch_id: int,
    subject_id: int,
    chapter_id: int | None,
    topic_id: int | None,
    concept_id: int | None,
    source_type: str,
    question_type: str,
    marks: int,
    difficulty: str,
    statement_md: str,
    correct_answer_json: dict,
    explanation_json: dict,
    options: list[dict] | None = None,
    nat_min: float | None = None,
    nat_max: float | None = None,
    exam_year: int | None = None,
    shift_session: str | None = None,
    original_question_number: str | None = None,
    page_number: int | None = None,
    attribution_text: str | None = None,
    paper_id: int | None = None,
    verification_status: str = "verified",
    is_published: bool = True,
    tags: list[str] | None = None,
    verifier_type: str = "official_key",
    verifier_tool: str = "seeded_verified",
) -> Question:
    """Create a complete Question with provenance, options, tags, and verification record."""
    source = QuestionSource(
        source_type=source_type,
        paper_id=paper_id,
        exam_year=exam_year,
        shift_session=shift_session,
        original_question_number=original_question_number,
        page_number=page_number,
        attribution_text=attribution_text,
    )
    db.session.add(source)
    db.session.flush()

    qtype = question_type.upper()
    neg = default_negative_marks(qtype, marks)

    question = Question(
        branch_id=branch_id,
        subject_id=subject_id,
        chapter_id=chapter_id,
        topic_id=topic_id,
        concept_id=concept_id,
        source_id=source.id,
        question_type=qtype,
        marks=marks,
        negative_marks=neg,
        difficulty=difficulty.lower(),
        statement_md=statement_md.strip(),
        normalized_hash=compute_normalized_hash(statement_md),
        correct_answer_json=correct_answer_json,
        nat_min=nat_min,
        nat_max=nat_max,
        explanation_json=explanation_json,
        verification_status=verification_status,
        is_published=is_published,
    )
    db.session.add(question)
    db.session.flush()

    if options:
        for idx, opt in enumerate(options, start=1):
            db.session.add(
                QuestionOption(
                    question_id=question.id,
                    label=opt["label"].upper(),
                    option_text_md=opt["text"],
                    is_correct=bool(opt.get("is_correct", False)),
                    display_order=idx,
                )
            )

    for tag_name in tags or []:
        clean_tag = tag_name.strip()
        if clean_tag:
            db.session.add(QuestionTag(question_id=question.id, tag_name=clean_tag))

    db.session.add(
        AnswerVerification(
            question_id=question.id,
            verifier_type=verifier_type,
            model_or_tool=verifier_tool,
            proposed_answer_json=correct_answer_json,
            is_match=(verification_status == "verified"),
            confidence_score=1.0 if verification_status == "verified" else 0.7,
            notes=f"Initial verification status: {verification_status}",
        )
    )
    return question


def query_question_bank(
    *,
    branch_id: int | None = None,
    subject_id: int | None = None,
    chapter_id: int | None = None,
    topic_id: int | None = None,
    source_type: str | None = None,
    question_type: str | None = None,
    difficulty: str | None = None,
    search: str | None = None,
    published_only: bool = True,
    page: int = 1,
    per_page: int = 15,
):
    """Paginated question bank query with safe joins."""
    q = Question.query.join(Question.source).options(
        joinedload(Question.subject),
        joinedload(Question.chapter),
        joinedload(Question.topic),
        joinedload(Question.concept),
        joinedload(Question.source),
        joinedload(Question.options),
    )

    if published_only:
        q = q.filter(Question.is_published.is_(True))
    if branch_id:
        q = q.filter(Question.branch_id == branch_id)
    if subject_id:
        q = q.filter(Question.subject_id == subject_id)
    if chapter_id:
        q = q.filter(Question.chapter_id == chapter_id)
    if topic_id:
        q = q.filter(Question.topic_id == topic_id)
    if source_type and source_type != "ALL":
        q = q.filter(QuestionSource.source_type == source_type)
    if question_type and question_type != "ALL":
        q = q.filter(Question.question_type == question_type)
    if difficulty and difficulty != "mixed":
        q = q.filter(Question.difficulty == difficulty)
    if search:
        like_term = f"%{search.strip()}%"
        q = q.filter(or_(Question.statement_md.ilike(like_term)))

    return q.order_by(Question.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
