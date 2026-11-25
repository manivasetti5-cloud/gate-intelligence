"""Personalization, longitudinal performance, AI advisor, revision plan, and formula library models."""

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
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def utcnow() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class FormulaEntry(db.Model):
    """Searchable GATE formula, mathematical identity, shortcut, and exam tip."""

    __tablename__ = "formula_library"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True
    )
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    formula_latex: Mapped[str] = mapped_column(Text, nullable=False)
    variables_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    shortcut_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    exam_tip_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    branch = relationship("Branch")
    subject = relationship("Subject")
    topic = relationship("Topic")


class StudentPerformance(db.Model):
    """Aggregated longitudinal student performance and internal GATE readiness metrics."""

    __tablename__ = "student_performance"
    __table_args__ = (UniqueConstraint("student_id", "branch_id", name="uq_student_perf_branch"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    total_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_accuracy: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    best_score_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_speed_sec: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    readiness_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    readiness_confidence_label: Mapped[str] = mapped_column(
        String(80), default="Insufficient Data", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class TopicPerformance(db.Model):
    """Per-topic longitudinal student accuracy and speed tracking."""

    __tablename__ = "topic_performance"
    __table_args__ = (UniqueConstraint("student_id", "topic_id", name="uq_student_topic_perf"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incorrect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accuracy_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_time_sec: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    strength_status: Mapped[str] = mapped_column(
        String(24), default="moderate", nullable=False
    )  # strong | moderate | weak
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    subject = relationship("Subject")
    topic = relationship("Topic")


class AIRecommendation(db.Model):
    """Structured AI Preparation Advisor report generated from real student history."""

    __tablename__ = "ai_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("student_attempts.id", ondelete="SET NULL"), nullable=True
    )
    summary_md: Mapped[str] = mapped_column(Text, nullable=False)
    weak_topics_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    strong_topics_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    suggested_formulas_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    recommended_test_config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    advice_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    model_used: Mapped[str] = mapped_column(String(80), default="rule_based_advisor", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RevisionPlan(db.Model):
    """Editable multi-day personalized preparation schedule."""

    __tablename__ = "revision_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    focus_subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    focus_subject = relationship("Subject")
    tasks: Mapped[list["RevisionTask"]] = relationship(
        "RevisionTask",
        back_populates="plan",
        order_by="RevisionTask.day_number",
        cascade="all, delete-orphan",
    )


class RevisionTask(db.Model):
    """Daily actionable item inside a student's RevisionPlan."""

    __tablename__ = "revision_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("revision_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), nullable=True
    )
    task_type: Mapped[str] = mapped_column(String(32), default="revise", nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped["RevisionPlan"] = relationship("RevisionPlan", back_populates="tasks")
    target_topic = relationship("Topic")
