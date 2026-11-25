"""Immediate test result evaluation dashboard and question-wise answer key review."""

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user
from sqlalchemy.orm import joinedload

from app.models.attempt import Bookmark, StudentAttempt
from app.models.question import Question
from app.models.test import Test, TestQuestion
from app.routes.student import _get_student_context
from app.services.auth_service import role_required
from app.services.evaluation_service import evaluate_attempt

results_bp = Blueprint("results", __name__, url_prefix="/results")


@results_bp.route("/<int:attempt_id>")
@role_required("student")
def view_result(attempt_id: int):
    """Display evaluated scorecard, breakdown charts, and detailed question explanations."""
    attempt = (
        StudentAttempt.query.options(
            joinedload(StudentAttempt.test)
            .joinedload(Test.test_questions)
            .joinedload(TestQuestion.question)
            .joinedload(Question.options),
            joinedload(StudentAttempt.test)
            .joinedload(Test.test_questions)
            .joinedload(TestQuestion.question)
            .joinedload(Question.source),
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
        .filter_by(id=attempt_id, student_id=current_user.id)
        .first_or_404()
    )

    # Prevent viewing answer keys if attempt is still active
    if attempt.status == "in_progress":
        return redirect(url_for("assessments.exam_interface", attempt_id=attempt.id))

    result = attempt.result or evaluate_attempt(attempt.id)
    resp_map = {r.test_question_id: r for r in attempt.responses}
    bookmarked_ids = {
        b.question_id for b in Bookmark.query.filter_by(student_id=current_user.id).all()
    }

    review_items = []
    for tq in attempt.test.test_questions:
        q = tq.question
        r = resp_map.get(tq.id)
        review_items.append(
            {
                "order_index": tq.order_index,
                "section_name": tq.section_name,
                "question": q,
                "response": r,
                "is_bookmarked": q.id in bookmarked_ids,
                "is_unverified": q.verification_status != "verified",
            }
        )

    ctx = _get_student_context()
    return render_template(
        "results/view.html",
        **ctx,
        attempt=attempt,
        result=result,
        review_items=review_items,
    )
