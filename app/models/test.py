"""Test configuration, generated assessment, and ordered test-question models."""

from datetime import date, datetime, timezone
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def utcnow() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class TestConfiguration(db.Model):
    """Student-selected or system-generated assessment parameters."""

    __tablename__ = "test_configurations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    syllabus_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("syllabus_versions.id", ondelete="SET NULL"), nullable=True
    )
    mode: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # concept | chapter | subject | full_mock | daily_challenge | reattempt
    target_scope_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    question_source: Mapped[str] = mapped_column(String(24), default="MIXED", nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), default="mixed", nullable=False)
    question_type: Mapped[str] = mapped_column(String(16), default="ALL", nullable=False)
    selection_mode: Mapped[str] = mapped_column(String(24), default="random", nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    is_pattern_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    branch = relationship("Branch")
    tests: Mapped[list["Test"]] = relationship("Test", back_populates="configuration")


class Test(db.Model):
    """Concrete generated test instance ready for student attempts."""

    __tablename__ = "tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("test_configurations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exam_pattern_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_patterns.id", ondelete="SET NULL"), nullable=True
    )
    total_marks: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    is_daily_challenge: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    challenge_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    configuration: Mapped["TestConfiguration"] = relationship(
        "TestConfiguration", back_populates="tests"
    )
    branch = relationship("Branch")
    exam_pattern = relationship("ExamPattern")
    test_questions: Mapped[list["TestQuestion"]] = relationship(
        "TestQuestion",
        back_populates="test",
        order_by="TestQuestion.order_index",
        cascade="all, delete-orphan",
    )


class TestQuestion(db.Model):
    """Ordered question slot inside a Test."""

    __tablename__ = "test_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_id: Mapped[int] = mapped_column(
        ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section_name: Mapped[str] = mapped_column(String(64), default="Technical", nullable=False)
    marks_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    negative_marks_override: Mapped[float | None] = mapped_column(Float, nullable=True)

    test: Mapped["Test"] = relationship("Test", back_populates="test_questions")
    question = relationship("Question")
