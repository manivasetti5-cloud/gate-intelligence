"""PDF paper upload, extraction jobs, extracted questions, and AI question generation models."""

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


class Paper(db.Model):
    """Uploaded GATE question paper metadata."""

    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exam_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    shift: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    source_authority: Mapped[str] = mapped_column(String(120), default="Official GATE PDF", nullable=False)
    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    branch = relationship("Branch")
    versions: Mapped[list["PaperVersion"]] = relationship(
        "PaperVersion", back_populates="paper", cascade="all, delete-orphan"
    )


class PaperVersion(db.Model):
    """Specific uploaded PDF file version for a Paper."""

    __tablename__ = "paper_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    paper: Mapped["Paper"] = relationship("Paper", back_populates="versions")
    jobs: Mapped[list["ExtractionJob"]] = relationship(
        "ExtractionJob", back_populates="paper_version", cascade="all, delete-orphan"
    )


class ExtractionJob(db.Model):
    """Background processing job tracking PDF extraction through verification."""

    __tablename__ = "extraction_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_version_id: Mapped[int] = mapped_column(
        ForeignKey("paper_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="uploaded", nullable=False, index=True
    )
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_detected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    paper_version: Mapped["PaperVersion"] = relationship("PaperVersion", back_populates="jobs")
    logs: Mapped[list["ExtractionLog"]] = relationship(
        "ExtractionLog", back_populates="job", order_by="ExtractionLog.created_at", cascade="all, delete-orphan"
    )
    extracted_questions: Mapped[list["ExtractedQuestion"]] = relationship(
        "ExtractedQuestion", back_populates="job", cascade="all, delete-orphan"
    )


class ExtractionLog(db.Model):
    """Stage-by-stage log entries for a PDF extraction job."""

    __tablename__ = "extraction_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("extraction_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    level: Mapped[str] = mapped_column(String(16), default="INFO", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    job: Mapped["ExtractionJob"] = relationship("ExtractionJob", back_populates="logs")


class ExtractedQuestion(db.Model):
    """Intermediate extracted question record awaiting verification or publication."""

    __tablename__ = "extracted_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("extraction_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    raw_q_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    crop_image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    structured_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    duplicate_of_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False, index=True
    )  # pending | approved | rejected | published
    linked_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )

    job: Mapped["ExtractionJob"] = relationship("ExtractionJob", back_populates="extracted_questions")
    linked_question = relationship("Question", foreign_keys=[linked_question_id])


class GenerationJob(db.Model):
    """Background job for generating original syllabus-aligned GATE questions."""

    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True
    )
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True
    )
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), nullable=True
    )
    concept_id: Mapped[int | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True
    )
    target_count: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    model_used: Mapped[str] = mapped_column(String(80), default="gemini", nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), default="v1.0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    branch = relationship("Branch")
    subject = relationship("Subject")
    logs: Mapped[list["GenerationLog"]] = relationship(
        "GenerationLog", back_populates="job", cascade="all, delete-orphan"
    )
    generated_items: Mapped[list["GeneratedQuestion"]] = relationship(
        "GeneratedQuestion", back_populates="job", cascade="all, delete-orphan"
    )


class GenerationLog(db.Model):
    """Log entry for an AI question generation job."""

    __tablename__ = "generation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[str] = mapped_column(String(16), default="INFO", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    job: Mapped["GenerationJob"] = relationship("GenerationJob", back_populates="logs")


class GeneratedQuestion(db.Model):
    """Provenance and quality tracking for an AI-generated original question."""

    __tablename__ = "generated_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_used: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), default="v1.0", nullable=False)
    schema_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    verification_passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    job: Mapped["GenerationJob"] = relationship("GenerationJob", back_populates="generated_items")
    question = relationship("Question")
