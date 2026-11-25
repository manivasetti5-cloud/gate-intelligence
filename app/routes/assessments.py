"""Assessment configuration, online examination session, autosave, submission, and test history routes."""

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.orm import joinedload

from app.models.attempt import StudentAttempt
from app.models.syllabus import Chapter, Concept, Subject, Topic
from app.models.test import Test
from app.routes.student import _get_student_context
from app.services.auth_service import role_required
from app.services.evaluation_service import evaluate_attempt
from app.services.exam_session_service import (
    save_student_response,
    serialize_exam_state,
    start_or_resume_attempt,
)
from app.services.syllabus_service import get_exam_pattern, get_syllabus_tree
from app.services.test_generator import generate_test, get_or_create_daily_challenge

assessments_bp = Blueprint("assessments", __name__, url_prefix="/assessments")


@assessments_bp.route("/configure")
@role_required("student")
def configure():
    """Render test configuration workspace (Concept, Chapter, Subject, Full Mock)."""
    ctx = _get_student_context()
    mode = request.args.get("mode", "subject")
    if mode not in ("concept", "chapter", "subject", "full_mock"):
        mode = "subject"

    subjects = (
        get_syllabus_tree(ctx["syllabus_version"].id) if ctx["syllabus_version"] else []
    )
    pattern = (
        get_exam_pattern(ctx["selected_branch"].id, ctx["exam_year"])
        if ctx["selected_branch"]
        else None
    )
    return render_template(
        "assessment/configure.html",
        **ctx,
        mode=mode,
        subjects=subjects,
        pattern=pattern,
    )


@assessments_bp.route("/api/cascade")
@role_required("student")
def syllabus_cascade():
    """Return nested chapters, topics, or concepts for dynamic test configuration dropdowns."""
    subject_id = request.args.get("subject_id", type=int)
    chapter_id = request.args.get("chapter_id", type=int)
    topic_id = request.args.get("topic_id", type=int)

    if subject_id:
        chapters = Chapter.query.filter_by(subject_id=subject_id).order_by(Chapter.display_order).all()
        return jsonify([{"id": c.id, "name": c.name} for c in chapters])
    if chapter_id:
        topics = Topic.query.filter_by(chapter_id=chapter_id).order_by(Topic.display_order).all()
        return jsonify([{"id": t.id, "name": t.name} for t in topics])
    if topic_id:
        concepts = Concept.query.filter_by(topic_id=topic_id).order_by(Concept.display_order).all()
        return jsonify([{"id": cp.id, "name": cp.name} for cp in concepts])
    return jsonify([])


@assessments_bp.route("/start", methods=["POST"])
@role_required("student")
def start():
    """Generate a test from submitted configuration and launch a timed attempt."""
    ctx = _get_student_context()
    branch = ctx["selected_branch"]
    if not branch:
        flash("Please select a GATE branch first.", "warning")
        return redirect(url_for("student.profile"))

    mode = request.form.get("mode", "subject")
    subject_id = request.form.get("subject_id", type=int)
    chapter_id = request.form.get("chapter_id", type=int)
    topic_id = request.form.get("topic_id", type=int)
    concept_id = request.form.get("concept_id", type=int)

    question_source = request.form.get("question_source", "MIXED")
    difficulty = request.form.get("difficulty", "mixed")
    question_type = request.form.get("question_type", "ALL")
    selection_mode = request.form.get("selection_mode", "random")
    question_count = request.form.get("question_count", type=int) or 10
    custom_count = request.form.get("custom_question_count", type=int)
    if custom_count and custom_count > 0:
        question_count = custom_count
    duration_minutes = request.form.get("duration_minutes", type=int)

    test, err = generate_test(
        student_id=current_user.id,
        branch_id=branch.id,
        exam_year=ctx["exam_year"],
        mode=mode,
        subject_id=subject_id,
        chapter_id=chapter_id,
        topic_id=topic_id,
        concept_id=concept_id,
        question_source=question_source,
        difficulty=difficulty,
        question_type=question_type,
        selection_mode=selection_mode,
        question_count=question_count,
        duration_minutes=duration_minutes,
    )
    if err or not test:
        flash(err or "Could not generate test.", "warning")
        return redirect(url_for("assessments.configure", mode=mode))

    attempt = start_or_resume_attempt(test.id, current_user.id, request.remote_addr)
    return redirect(url_for("assessments.exam_interface", attempt_id=attempt.id))


@assessments_bp.route("/daily-challenge")
@role_required("student")
def daily_challenge():
    """Launch or resume today's Daily Challenge for the student's active branch."""
    ctx = _get_student_context()
    branch = ctx["selected_branch"]
    if not branch:
        flash("Select a branch to take the Daily Challenge.", "warning")
        return redirect(url_for("student.profile"))

    test, err = get_or_create_daily_challenge(current_user.id, branch.id, ctx["exam_year"])
    if err or not test:
        flash(err or "No questions available for today's Daily Challenge yet.", "warning")
        return redirect(url_for("student.dashboard"))

    # If already submitted today's challenge, go directly to result
    done_attempt = StudentAttempt.query.filter(
        StudentAttempt.test_id == test.id,
        StudentAttempt.student_id == current_user.id,
        StudentAttempt.status.in_(["submitted", "auto_submitted"]),
    ).first()
    if done_attempt:
        flash("You have already completed today's Daily Challenge. Viewing your result.", "info")
        return redirect(url_for("results.view_result", attempt_id=done_attempt.id))

    attempt = start_or_resume_attempt(test.id, current_user.id, request.remote_addr)
    return redirect(url_for("assessments.exam_interface", attempt_id=attempt.id))


@assessments_bp.route("/reattempt", methods=["POST"])
@role_required("student")
def reattempt():
    """Generate a targeted reattempt test (incorrect, unattempted, bookmarked, or weak_topic)."""
    ctx = _get_student_context()
    branch = ctx["selected_branch"]
    if not branch:
        flash("Select a GATE branch first.", "warning")
        return redirect(url_for("student.profile"))

    selection_mode = request.form.get("selection_mode", "incorrect")
    if selection_mode not in ("incorrect", "unattempted", "bookmarked", "weak_topic"):
        selection_mode = "incorrect"

    test, err = generate_test(
        student_id=current_user.id,
        branch_id=branch.id,
        exam_year=ctx["exam_year"],
        mode="reattempt",
        question_source="MIXED",
        difficulty="mixed",
        question_type="ALL",
        selection_mode=selection_mode,
        question_count=request.form.get("question_count", type=int) or 20,
    )
    if err or not test:
        flash(err or "No matching questions found for reattempt.", "info")
        return redirect(request.referrer or url_for("student.dashboard"))

    attempt = start_or_resume_attempt(test.id, current_user.id, request.remote_addr)
    return redirect(url_for("assessments.exam_interface", attempt_id=attempt.id))


@assessments_bp.route("/exam/<int:attempt_id>")
@role_required("student")
def exam_interface(attempt_id: int):
    """Render the distraction-free GATE CBT examination screen."""
    attempt = (
        StudentAttempt.query.options(joinedload(StudentAttempt.test))
        .filter_by(id=attempt_id, student_id=current_user.id)
        .first_or_404()
    )
    if attempt.status in ("submitted", "auto_submitted"):
        return redirect(url_for("results.view_result", attempt_id=attempt.id))

    initial_state = serialize_exam_state(attempt.id, current_user.id)
    if initial_state.get("redirect_to_result"):
        return redirect(url_for("results.view_result", attempt_id=attempt.id))

    return render_template(
        "assessment/exam.html",
        attempt=attempt,
        initial_state=initial_state,
    )


@assessments_bp.route("/exam/<int:attempt_id>/state", methods=["GET"])
@role_required("student")
def exam_state(attempt_id: int):
    """JSON endpoint returning server-authoritative exam state (never includes answers)."""
    payload = serialize_exam_state(attempt_id, current_user.id)
    return jsonify(payload)


@assessments_bp.route("/exam/<int:attempt_id>/save", methods=["POST"])
@role_required("student")
def save_response(attempt_id: int):
    """Autosave student answer and palette status for a question."""
    data = request.get_json(silent=True) or {}
    tq_id = data.get("test_question_id")
    if not tq_id:
        return jsonify({"error": "test_question_id is required"}), 400

    payload, status_code = save_student_response(
        attempt_id=attempt_id,
        student_id=current_user.id,
        test_question_id=int(tq_id),
        selected_options=data.get("selected_options", []),
        nat_answer_raw=data.get("nat_answer_value"),
        palette_status=data.get("palette_status", "visited_unanswered"),
        current_question_index=data.get("current_question_index"),
        time_delta_seconds=int(data.get("time_delta_seconds") or 0),
    )
    return jsonify(payload), status_code


@assessments_bp.route("/exam/<int:attempt_id>/submit", methods=["POST"])
@role_required("student")
def submit_exam(attempt_id: int):
    """Finalize and evaluate a student's test attempt server-side."""
    attempt = StudentAttempt.query.filter_by(
        id=attempt_id, student_id=current_user.id
    ).first_or_404()

    is_auto = False
    if request.is_json:
        is_auto = bool((request.get_json(silent=True) or {}).get("auto_submit"))
    else:
        is_auto = request.form.get("auto_submit") == "1"

    evaluate_attempt(attempt.id, auto_submitted=is_auto)
    if request.is_json:
        return jsonify({"submitted": True, "redirect_url": url_for("results.view_result", attempt_id=attempt.id)})
    return redirect(url_for("results.view_result", attempt_id=attempt.id))


@assessments_bp.route("/history")
@role_required("student")
def history():
    """List all student test attempts with scores, accuracy, and review/resume links."""
    ctx = _get_student_context()
    attempts = (
        StudentAttempt.query.options(
            joinedload(StudentAttempt.test).joinedload(Test.configuration),
            joinedload(StudentAttempt.result),
        )
        .filter_by(student_id=current_user.id)
        .order_by(StudentAttempt.started_at.desc())
        .all()
    )
    return render_template("assessment/history.html", **ctx, attempts=attempts)
