"""Server-authoritative examination session lifecycle and anti-leak state serialization."""

from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.attempt import StudentAttempt, StudentResponse, TestSession
from app.models.question import Question
from app.models.test import Test, TestQuestion
from app.services.auth_service import log_audit
from app.services.evaluation_service import evaluate_attempt


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def start_or_resume_attempt(test_id: int, student_id: int, client_ip: str | None = None) -> StudentAttempt:
    """Resume an active in-progress attempt for this test or initialize a fresh timed attempt."""
    existing = (
        StudentAttempt.query.filter_by(
            test_id=test_id, student_id=student_id, status="in_progress"
        )
        .order_by(StudentAttempt.id.desc())
        .first()
    )
    if existing:
        if utcnow() >= _ensure_utc(existing.expires_at):
            evaluate_attempt(existing.id, auto_submitted=True)
        else:
            return existing

    test = Test.query.options(joinedload(Test.test_questions)).get_or_404(test_id)
    now = utcnow()
    expires = now + timedelta(minutes=test.duration_minutes)

    attempt = StudentAttempt(
        test_id=test.id,
        student_id=student_id,
        status="in_progress",
        started_at=now,
        expires_at=expires,
    )
    db.session.add(attempt)
    db.session.flush()

    ip_hash = hashlib.sha256((client_ip or "").encode("utf-8")).hexdigest()[:32]
    session = TestSession(
        attempt_id=attempt.id,
        session_token=secrets.token_urlsafe(32),
        current_question_index=0,
        last_heartbeat_at=now,
        client_ip_hash=ip_hash,
    )
    db.session.add(session)

    for idx, tq in enumerate(test.test_questions):
        db.session.add(
            StudentResponse(
                attempt_id=attempt.id,
                test_question_id=tq.id,
                question_id=tq.question_id,
                selected_options_json=[],
                nat_answer_value=None,
                palette_status="visited_unanswered" if idx == 0 else "not_visited",
                time_spent_seconds=0,
            )
        )

    log_audit(
        action="exam.attempt_start",
        entity_type="student_attempt",
        entity_id=attempt.id,
        details={"test_id": test.id, "duration_minutes": test.duration_minutes},
        actor_user_id=student_id,
    )
    db.session.commit()
    return attempt


def check_expiry_and_auto_submit(attempt: StudentAttempt) -> bool:
    """Return True if attempt is expired and was auto-submitted."""
    if attempt.status != "in_progress":
        return attempt.status in ("submitted", "auto_submitted")
    if utcnow() >= _ensure_utc(attempt.expires_at):
        evaluate_attempt(attempt.id, auto_submitted=True)
        return True
    return False


def serialize_exam_state(attempt_id: int, student_id: int) -> dict:
    """Serialize active exam state WITHOUT any answer keys, correctness flags, or explanations."""
    attempt = (
        StudentAttempt.query.options(
            joinedload(StudentAttempt.test)
            .joinedload(Test.test_questions)
            .joinedload(TestQuestion.question)
            .joinedload(Question.options),
            joinedload(StudentAttempt.test)
            .joinedload(Test.test_questions)
            .joinedload(TestQuestion.question)
            .joinedload(Question.images),
            joinedload(StudentAttempt.test)
            .joinedload(Test.test_questions)
            .joinedload(TestQuestion.question)
            .joinedload(Question.source),
            joinedload(StudentAttempt.session),
            joinedload(StudentAttempt.responses),
        )
        .filter_by(id=attempt_id, student_id=student_id)
        .first_or_404()
    )

    if check_expiry_and_auto_submit(attempt):
        return {
            "status": attempt.status,
            "redirect_to_result": True,
            "attempt_id": attempt.id,
        }

    resp_by_tq = {r.test_question_id: r for r in attempt.responses}
    now = utcnow()
    remaining_seconds = max(0, int((_ensure_utc(attempt.expires_at) - now).total_seconds()))

    questions_payload = []
    for tq in attempt.test.test_questions:
        q = tq.question
        r = resp_by_tq.get(tq.id)
        marks = tq.marks_override if tq.marks_override is not None else q.marks
        neg = (
            tq.negative_marks_override
            if tq.negative_marks_override is not None
            else q.negative_marks
        )
        # IMPORTANT: Do NOT include is_correct, correct_answer_json, or explanation_json here.
        questions_payload.append(
            {
                "test_question_id": tq.id,
                "order_index": tq.order_index,
                "section_name": tq.section_name,
                "question_type": q.question_type,
                "marks": marks,
                "negative_marks": round(neg, 2),
                "difficulty": q.difficulty,
                "source_type": q.source.source_type if q.source else "UNKNOWN",
                "statement_md": q.statement_md,
                "options": [
                    {"label": opt.label, "text": opt.option_text_md} for opt in q.options
                ],
                "images": [
                    {"file_path": img.file_path, "caption": img.caption} for img in q.images
                ],
                "response": {
                    "selected_options": r.selected_options_json if r else [],
                    "nat_answer_value": r.nat_answer_value if r else None,
                    "palette_status": r.palette_status if r else "not_visited",
                    "time_spent_seconds": r.time_spent_seconds if r else 0,
                },
            }
        )

    return {
        "attempt_id": attempt.id,
        "test_id": attempt.test.id,
        "test_title": attempt.test.title,
        "status": attempt.status,
        "remaining_seconds": remaining_seconds,
        "current_question_index": attempt.session.current_question_index if attempt.session else 0,
        "questions": questions_payload,
    }


def save_student_response(
    *,
    attempt_id: int,
    student_id: int,
    test_question_id: int,
    selected_options: list[str] | None,
    nat_answer_raw: str | float | None,
    palette_status: str,
    current_question_index: int | None = None,
    time_delta_seconds: int = 0,
) -> tuple[dict, int]:
    """Persist student response and palette state server-side during an active exam."""
    attempt = StudentAttempt.query.filter_by(id=attempt_id, student_id=student_id).first()
    if not attempt:
        return {"error": "Attempt not found"}, 404

    if attempt.status != "in_progress":
        return {"error": "Attempt already submitted", "status": attempt.status}, 409

    # Allow 3-second grace window for in-flight autosave right at countdown 0
    now = utcnow()
    if now > _ensure_utc(attempt.expires_at) + timedelta(seconds=3):
        evaluate_attempt(attempt.id, auto_submitted=True)
        return {"error": "Time expired; test auto-submitted", "status": "auto_submitted"}, 409

    response = StudentResponse.query.filter_by(
        attempt_id=attempt.id, test_question_id=test_question_id
    ).first()
    if not response:
        return {"error": "Question not in this test"}, 404

    allowed_statuses = {
        "not_visited",
        "visited_unanswered",
        "answered",
        "marked_for_review",
        "answered_and_marked",
    }
    clean_status = palette_status if palette_status in allowed_statuses else "visited_unanswered"

    clean_options = sorted({str(opt).upper() for opt in (selected_options or []) if opt})
    nat_val: float | None = None
    if nat_answer_raw is not None and str(nat_answer_raw).strip() != "":
        try:
            nat_val = float(str(nat_answer_raw).strip())
        except ValueError:
            return {"error": "Numerical answer must be a valid number."}, 400

    response.selected_options_json = clean_options
    response.nat_answer_value = nat_val
    response.palette_status = clean_status
    if time_delta_seconds and time_delta_seconds > 0:
        response.time_spent_seconds += min(600, int(time_delta_seconds))

    if attempt.session:
        attempt.session.last_heartbeat_at = now
        if current_question_index is not None:
            attempt.session.current_question_index = max(0, int(current_question_index))

    db.session.commit()
    remaining_seconds = max(0, int((_ensure_utc(attempt.expires_at) - utcnow()).total_seconds()))
    return {
        "saved": True,
        "palette_status": response.palette_status,
        "remaining_seconds": remaining_seconds,
    }, 200
