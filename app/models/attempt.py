"""Student attempt, server session state, responses, results, bookmarks, and error notebook."""

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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def utcnow() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class StudentAttempt(db.Model):
    """Server-authoritative record of a student's attempt at a Test."""

    __tablename__ = "student_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_id: Mapped[int] = mapped_column(
        ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(24), default="in_progress", nullable=False, index=True
    )  # in_progress | submitted | auto_submitted | abandoned
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_taken_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    test = relationship("Test")
    student = relationship("User")
    session: Mapped["TestSession | None"] = relationship(
        "TestSession", back_populates="attempt", uselist=False, cascade="all, delete-orphan"
    )
    responses: Mapped[list["StudentResponse"]] = relationship(
        "StudentResponse", back_populates="attempt", cascade="all, delete-orphan"
    )
    result: Mapped["Result | None"] = relationship(
        "Result", back_populates="attempt", uselist=False, cascade="all, delete-orphan"
    )


class TestSession(db.Model):
    """Active test session recovery and heartbeat metadata."""

    __tablename__ = "test_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("student_attempts.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    session_token: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    current_question_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    client_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    attempt: Mapped["StudentAttempt"] = relationship("StudentAttempt", back_populates="session")


class StudentResponse(db.Model):
    """Per-question answer and palette state during and after an attempt."""

    __tablename__ = "student_responses"
    __table_args__ = (
        UniqueConstraint("attempt_id", "test_question_id", name="uq_attempt_test_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("student_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    test_question_id: Mapped[int] = mapped_column(
        ForeignKey("test_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    selected_options_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    nat_answer_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    palette_status: Mapped[str] = mapped_column(
        String(32), default="not_visited", nullable=False
    )  # not_visited | visited_unanswered | answered | marked_for_review | answered_and_marked
    time_spent_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    marks_awarded: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    attempt: Mapped["StudentAttempt"] = relationship("StudentAttempt", back_populates="responses")
    test_question = relationship("TestQuestion")
    question = relationship("Question")


class Result(db.Model):
    """Evaluated scorecard and multi-dimensional breakdown for a submitted attempt."""

    __tablename__ = "results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("student_attempts.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    total_marks_obtained: Mapped[float] = mapped_column(Float, nullable=False)
    max_marks: Mapped[float] = mapped_column(Float, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incorrect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unanswered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accuracy_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_time_per_question: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    breakdown_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    attempt: Mapped["StudentAttempt"] = relationship("StudentAttempt", back_populates="result")


class Bookmark(db.Model):
    """Student-bookmarked questions for quick revision or reattempt."""

    __tablename__ = "bookmarks"
    __table_args__ = (UniqueConstraint("student_id", "question_id", name="uq_bookmark_student_q"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    question = relationship("Question")


class ErrorNotebookEntry(db.Model):
    """Automatically captured incorrect questions grouped for revision and reattempt."""

    __tablename__ = "error_notebook"
    __table_args__ = (UniqueConstraint("student_id", "question_id", name="uq_error_student_q"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    last_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("student_attempts.id", ondelete="SET NULL"), nullable=True
    )
    mistake_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="unresolved", nullable=False, index=True
    )  # unresolved | reattempted_correct | mastered
    personal_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    question = relationship("Question")
