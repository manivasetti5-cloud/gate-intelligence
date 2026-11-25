"""Server-side GATE examination scoring and result breakdown service."""

from datetime import datetime, timezone

from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.attempt import (
    ErrorNotebookEntry,
    Result,
    StudentAttempt,
    StudentResponse,
)
from app.models.question import Question
from app.models.test import Test, TestQuestion
from app.services.auth_service import log_audit


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def score_question_response(
    question: Question,
    response: StudentResponse,
    marks_override: float | None = None,
    negative_override: float | None = None,
) -> tuple[bool | None, float, str]:
    """
    Evaluate a single response strictly using official GATE rules.
    Returns (is_correct_or_none, marks_awarded, status_label).
    """
    qtype = question.question_type.upper()
    marks = float(marks_override if marks_override is not None else question.marks)
    neg = float(negative_override if negative_override is not None else question.negative_marks)
    correct_json = question.correct_answer_json or {}

    if qtype == "MCQ":
        selected = [s.upper() for s in (response.selected_options_json or [])]
        if not selected:
            return None, 0.0, "unanswered"
        target = str(correct_json.get("option", "")).upper()
        if len(selected) == 1 and selected[0] == target:
            return True, marks, "correct"
        return False, -abs(neg), "incorrect"

    if qtype == "MSQ":
        selected = {s.upper() for s in (response.selected_options_json or [])}
        if not selected:
            return None, 0.0, "unanswered"
        targets = {str(o).upper() for o in correct_json.get("options", [])}
        if selected == targets and len(targets) > 0:
            return True, marks, "correct"
        # Official GATE MSQ has no negative marking and no partial credit
        return False, 0.0, "incorrect"

    if qtype == "NAT":
        val = response.nat_answer_value
        if val is None:
            return None, 0.0, "unanswered"
        low = question.nat_min
        high = question.nat_max
        if low is None or high is None:
            exact = correct_json.get("value")
            if exact is None:
                return False, 0.0, "incorrect"
            low = float(exact) - 1e-4
            high = float(exact) + 1e-4
        if float(low) - 1e-6 <= float(val) <= float(high) + 1e-6:
            return True, marks, "correct"
        # Official GATE NAT has no negative marking
        return False, 0.0, "incorrect"

    return None, 0.0, "unanswered"


def _accumulate_bucket(bucket_map: dict, key: str, marks_awarded: float, max_marks: float, status: str) -> None:
    entry = bucket_map.setdefault(
        key,
        {
            "label": key,
            "total": 0,
            "correct": 0,
            "incorrect": 0,
            "unanswered": 0,
            "marks_obtained": 0.0,
            "max_marks": 0.0,
        },
    )
    entry["total"] += 1
    entry[status] += 1
    entry["marks_obtained"] = round(entry["marks_obtained"] + marks_awarded, 2)
    entry["max_marks"] = round(entry["max_marks"] + max_marks, 2)


def evaluate_attempt(attempt_id: int, auto_submitted: bool = False) -> Result:
    """Idempotently score an attempt, store Result, and update Error Notebook."""
    attempt = (
        StudentAttempt.query.options(
            joinedload(StudentAttempt.test)
            .joinedload(Test.test_questions)
            .joinedload(TestQuestion.question)
            .joinedload(Question.subject),
            joinedload(StudentAttempt.test)
            .joinedload(Test.test_questions)
            .joinedload(TestQuestion.question)
            .joinedload(Question.chapter),
            joinedload(StudentAttempt.test)
            .joinedload(Test.test_questions)
            .joinedload(TestQuestion.question)
            .joinedload(Question.topic),
            joinedload(StudentAttempt.responses),
            joinedload(StudentAttempt.result),
        )
        .filter_by(id=attempt_id)
        .first_or_404()
    )

    if attempt.result and attempt.status in ("submitted", "auto_submitted"):
        return attempt.result

    now = utcnow()
    started = _ensure_utc(attempt.started_at)
    expires = _ensure_utc(attempt.expires_at)
    effective_end = min(now, expires) if auto_submitted else now
    time_taken = max(0, int((effective_end - started).total_seconds()))

    attempt.status = "auto_submitted" if auto_submitted else "submitted"
    attempt.submitted_at = effective_end
    attempt.time_taken_seconds = time_taken

    tq_map = {tq.id: tq for tq in attempt.test.test_questions}

    total_marks_obtained = 0.0
    max_marks = 0.0
    correct_count = 0
    incorrect_count = 0
    unanswered_count = 0

    by_subject: dict = {}
    by_chapter: dict = {}
    by_topic: dict = {}
    by_difficulty: dict = {}
    by_qtype: dict = {}

    for resp in attempt.responses:
        tq = tq_map.get(resp.test_question_id)
        if not tq:
            continue
        q = tq.question
        q_max = float(tq.marks_override if tq.marks_override is not None else q.marks)
        max_marks += q_max

        is_correct, awarded, status_label = score_question_response(
            q, resp, tq.marks_override, tq.negative_marks_override
        )
        resp.is_correct = is_correct
        resp.marks_awarded = round(awarded, 4)
        total_marks_obtained += awarded

        if status_label == "correct":
            correct_count += 1
        elif status_label == "incorrect":
            incorrect_count += 1
        else:
            unanswered_count += 1

        subj_name = q.subject.name if q.subject else "General"
        chap_name = q.chapter.name if q.chapter else "General"
        topic_name = q.topic.name if q.topic else "General"

        _accumulate_bucket(by_subject, subj_name, awarded, q_max, status_label)
        _accumulate_bucket(by_chapter, chap_name, awarded, q_max, status_label)
        _accumulate_bucket(by_topic, topic_name, awarded, q_max, status_label)
        _accumulate_bucket(by_difficulty, q.difficulty.title(), awarded, q_max, status_label)
        _accumulate_bucket(by_qtype, q.question_type.upper(), awarded, q_max, status_label)

        # Update Error Notebook automatically
        existing_err = ErrorNotebookEntry.query.filter_by(
            student_id=attempt.student_id, question_id=q.id
        ).first()
        if status_label == "incorrect":
            if existing_err:
                existing_err.mistake_count += 1
                existing_err.last_attempt_id = attempt.id
                existing_err.status = "unresolved"
            else:
                db.session.add(
                    ErrorNotebookEntry(
                        student_id=attempt.student_id,
                        question_id=q.id,
                        last_attempt_id=attempt.id,
                        mistake_count=1,
                        status="unresolved",
                    )
                )
        elif status_label == "correct" and existing_err and existing_err.status == "unresolved":
            existing_err.status = "reattempted_correct"
            existing_err.last_attempt_id = attempt.id

    attempted_total = correct_count + incorrect_count
    accuracy = round((correct_count / attempted_total) * 100.0, 2) if attempted_total > 0 else 0.0
    total_q_count = len(attempt.responses)
    avg_time = round(time_taken / total_q_count, 2) if total_q_count > 0 else 0.0

    for bucket in (by_subject, by_chapter, by_topic, by_difficulty, by_qtype):
        for stats in bucket.values():
            att = stats["correct"] + stats["incorrect"]
            stats["accuracy_percent"] = round((stats["correct"] / att) * 100.0, 1) if att > 0 else 0.0

    result = Result(
        attempt_id=attempt.id,
        total_marks_obtained=round(total_marks_obtained, 2),
        max_marks=round(max_marks, 2),
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        unanswered_count=unanswered_count,
        accuracy_percent=accuracy,
        avg_time_per_question=avg_time,
        breakdown_json={
            "subject": list(by_subject.values()),
            "chapter": list(by_chapter.values()),
            "topic": list(by_topic.values()),
            "difficulty": list(by_difficulty.values()),
            "question_type": list(by_qtype.values()),
        },
    )
    db.session.add(result)

    log_audit(
        action="exam.attempt_evaluated",
        entity_type="student_attempt",
        entity_id=attempt.id,
        details={
            "auto_submitted": auto_submitted,
            "marks": result.total_marks_obtained,
            "max_marks": result.max_marks,
        },
        actor_user_id=attempt.student_id,
    )
    db.session.commit()

    from app.services.analytics_service import refresh_student_analytics

    refresh_student_analytics(attempt.student_id, attempt.test.branch_id)
    return result
