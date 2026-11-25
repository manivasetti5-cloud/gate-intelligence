"""Question bank, source provenance, options, images, tags, and answer verification models."""

from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def utcnow() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class QuestionSource(db.Model):
    """Provenance record distinguishing PYQ and AI_GENERATED questions."""

    __tablename__ = "question_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # PYQ | AI_GENERATED
    paper_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    exam_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    shift_session: Mapped[str | None] = mapped_column(String(32), nullable=True)
    original_question_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attribution_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    questions: Mapped[list["Question"]] = relationship("Question", back_populates="source")


class Question(db.Model):
    """Central GATE question record across MCQ, MSQ, and NAT formats."""

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), nullable=True, index=True
    )
    concept_id: Mapped[int | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("question_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    question_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # MCQ | MSQ | NAT
    marks: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1 or 2
    negative_marks: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), default="medium", nullable=False, index=True)

    statement_md: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Answer fields (NEVER serialized during active exam sessions)
    correct_answer_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    nat_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    nat_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    explanation_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    verification_status: Mapped[str] = mapped_column(
        String(40), default="needs_manual_review", nullable=False, index=True
    )  # verified | ai_solved_awaiting_verification | needs_manual_review
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_outdated_syllabus: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    branch = relationship("Branch")
    subject = relationship("Subject")
    chapter = relationship("Chapter")
    topic = relationship("Topic")
    concept = relationship("Concept")
    source: Mapped["QuestionSource"] = relationship("QuestionSource", back_populates="questions")
    options: Mapped[list["QuestionOption"]] = relationship(
        "QuestionOption",
        back_populates="question",
        order_by="QuestionOption.display_order",
        cascade="all, delete-orphan",
    )
    images: Mapped[list["QuestionImage"]] = relationship(
        "QuestionImage", back_populates="question", cascade="all, delete-orphan"
    )
    tags: Mapped[list["QuestionTag"]] = relationship(
        "QuestionTag", back_populates="question", cascade="all, delete-orphan"
    )
    verifications: Mapped[list["AnswerVerification"]] = relationship(
        "AnswerVerification", back_populates="question", cascade="all, delete-orphan"
    )
    history_entries: Mapped[list["QuestionHistory"]] = relationship(
        "QuestionHistory", back_populates="question", cascade="all, delete-orphan"
    )


class QuestionOption(db.Model):
    """Answer choices for MCQ and MSQ questions."""

    __tablename__ = "question_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(8), nullable=False)  # A, B, C, D
    option_text_md: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    question: Mapped["Question"] = relationship("Question", back_populates="options")


class QuestionImage(db.Model):
    """Preserved diagrams, circuit schematics, graphs, and page crops."""

    __tablename__ = "question_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    caption: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_type: Mapped[str] = mapped_column(String(32), default="diagram", nullable=False)
    perceptual_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    question: Mapped["Question"] = relationship("Question", back_populates="images")


class QuestionTag(db.Model):
    """Searchable conceptual tags attached to questions."""

    __tablename__ = "question_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    question: Mapped["Question"] = relationship("Question", back_populates="tags")


class AnswerVerification(db.Model):
    """Independent verification trail for every question's answer key."""

    __tablename__ = "answer_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    verifier_type: Mapped[str] = mapped_column(
        String(40), nullable=False
    )  # sympy_numeric | second_llm | human_admin | official_key
    model_or_tool: Mapped[str] = mapped_column(String(80), nullable=False)
    proposed_answer_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_match: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    question: Mapped["Question"] = relationship("Question", back_populates="verifications")


class QuestionHistory(db.Model):
    """Revision audit trail for edits to questions or answer keys."""

    __tablename__ = "question_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    changed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    change_type: Mapped[str] = mapped_column(String(48), nullable=False)
    diff_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    question: Mapped["Question"] = relationship("Question", back_populates="history_entries")
