"""GATE branch, syllabus hierarchy, version, and exam pattern models."""

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


class Branch(db.Model):
    """Supported GATE engineering branches (CS, DA, EC, ME, EE)."""

    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    syllabus_versions: Mapped[list["SyllabusVersion"]] = relationship(
        "SyllabusVersion", back_populates="branch", cascade="all, delete-orphan"
    )
    exam_patterns: Mapped[list["ExamPattern"]] = relationship(
        "ExamPattern", back_populates="branch", cascade="all, delete-orphan"
    )


class SyllabusVersion(db.Model):
    """Year-specific official GATE syllabus version for a branch."""

    __tablename__ = "syllabus_versions"
    __table_args__ = (
        UniqueConstraint("branch_id", "exam_year", "version_label", name="uq_syllabus_branch_year_ver"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exam_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    version_label: Mapped[str] = mapped_column(String(64), default="Official v1.0", nullable=False)
    syllabus_source: Mapped[str] = mapped_column(String(255), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    branch: Mapped["Branch"] = relationship("Branch", back_populates="syllabus_versions")
    subjects: Mapped[list["Subject"]] = relationship(
        "Subject",
        back_populates="syllabus_version",
        order_by="Subject.display_order",
        cascade="all, delete-orphan",
    )


class Subject(db.Model):
    """Subject within a syllabus version (e.g., Data Structures, General Aptitude)."""

    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    syllabus_version_id: Mapped[int] = mapped_column(
        ForeignKey("syllabus_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(24), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    weightage_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_general_aptitude: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)

    syllabus_version: Mapped["SyllabusVersion"] = relationship(
        "SyllabusVersion", back_populates="subjects"
    )
    chapters: Mapped[list["Chapter"]] = relationship(
        "Chapter",
        back_populates="subject",
        order_by="Chapter.display_order",
        cascade="all, delete-orphan",
    )


class Chapter(db.Model):
    """Chapter within a GATE subject."""

    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_outdated_in_latest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    subject: Mapped["Subject"] = relationship("Subject", back_populates="chapters")
    topics: Mapped[list["Topic"]] = relationship(
        "Topic",
        back_populates="chapter",
        order_by="Topic.display_order",
        cascade="all, delete-orphan",
    )


class Topic(db.Model):
    """Topic within a chapter."""

    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_outdated_in_latest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    chapter: Mapped["Chapter"] = relationship("Chapter", back_populates="topics")
    concepts: Mapped[list["Concept"]] = relationship(
        "Concept",
        back_populates="topic",
        order_by="Concept.display_order",
        cascade="all, delete-orphan",
    )


class Concept(db.Model):
    """Granular concept within a topic."""

    __tablename__ = "concepts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(220), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_outdated_in_latest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    topic: Mapped["Topic"] = relationship("Topic", back_populates="concepts")


class ExamPattern(db.Model):
    """Official GATE examination pattern per branch and year."""

    __tablename__ = "exam_patterns"
    __table_args__ = (UniqueConstraint("branch_id", "exam_year", name="uq_pattern_branch_year"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exam_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=180, nullable=False)
    total_marks: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    total_questions: Mapped[int] = mapped_column(Integer, default=65, nullable=False)
    ga_marks: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    technical_marks: Mapped[int] = mapped_column(Integer, default=85, nullable=False)
    rules_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    branch: Mapped["Branch"] = relationship("Branch", back_populates="exam_patterns")
