"""Student performance analytics, AI advisor, GATE readiness, revision plans, and formula library routes."""

from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.orm import joinedload

from app.extensions import db, limiter
from app.models.analytics import (
    AIRecommendation,
    FormulaEntry,
    RevisionPlan,
    RevisionTask,
)
from app.routes.student import _get_student_context
from app.services.analytics_service import get_student_analytics_bundle
from app.services.auth_service import role_required
from app.services.recommendation_engine import (
    create_seven_day_revision_plan,
    generate_personalized_recommendation,
)
from app.services.syllabus_service import get_syllabus_tree

analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")


@analytics_bp.route("/performance")
@role_required("student")
def performance():
    """Longitudinal student performance analytics with Chart.js visualizations."""
    ctx = _get_student_context()
    branch = ctx["selected_branch"]
    bundle = (
        get_student_analytics_bundle(current_user.id, branch.id)
        if branch
        else None
    )
    return render_template("student/performance.html", **ctx, bundle=bundle)


@analytics_bp.route("/readiness")
@role_required("student")
def readiness():
    """Internal GATE Readiness Tracker clearly labeled as a diagnostic estimate."""
    ctx = _get_student_context()
    branch = ctx["selected_branch"]
    bundle = (
        get_student_analytics_bundle(current_user.id, branch.id)
        if branch
        else None
    )
    return render_template("student/readiness.html", **ctx, bundle=bundle)


@analytics_bp.route("/advisor", methods=["GET", "POST"])
@role_required("student")
@limiter.limit("12 per minute")
def advisor():
    """AI Personalized Preparation Advisor view and generator."""
    ctx = _get_student_context()
    branch = ctx["selected_branch"]

    if request.method == "POST" and branch:
        generate_personalized_recommendation(current_user.id, branch.id)
        flash("Personalized AI preparation report updated from your assessment history.", "success")
        return redirect(url_for("analytics.advisor"))

    latest_rec = (
        AIRecommendation.query.filter_by(student_id=current_user.id)
        .order_by(AIRecommendation.created_at.desc())
        .first()
    )
    if branch:
        from app.models.attempt import StudentAttempt

        latest_attempt = (
            StudentAttempt.query.filter(
                StudentAttempt.student_id == current_user.id,
                StudentAttempt.status.in_(["submitted", "auto_submitted"]),
            )
            .order_by(StudentAttempt.submitted_at.desc())
            .first()
        )
        needs_refresh = latest_rec is None or (
            latest_attempt
            and latest_attempt.submitted_at
            and latest_rec.created_at
            and latest_attempt.submitted_at > latest_rec.created_at
        )
        if needs_refresh:
            latest_rec = generate_personalized_recommendation(
                current_user.id,
                branch.id,
                attempt_id=latest_attempt.id if latest_attempt else None,
            )

    return render_template("student/advisor.html", **ctx, recommendation=latest_rec)


@analytics_bp.route("/revision", methods=["GET"])
@role_required("student")
def revision():
    """Manage and track editable 7-day personalized preparation plans."""
    ctx = _get_student_context()
    subjects = (
        get_syllabus_tree(ctx["syllabus_version"].id) if ctx["syllabus_version"] else []
    )
    plans = (
        RevisionPlan.query.options(
            joinedload(RevisionPlan.tasks), joinedload(RevisionPlan.focus_subject)
        )
        .filter_by(student_id=current_user.id)
        .order_by(RevisionPlan.created_at.desc())
        .all()
    )
    return render_template("student/revision.html", **ctx, plans=plans, subjects=subjects)


@analytics_bp.route("/revision/generate", methods=["POST"])
@role_required("student")
def generate_revision_plan():
    """Create a 7-day personalized revision schedule."""
    ctx = _get_student_context()
    branch = ctx["selected_branch"]
    if not branch:
        flash("Select a branch first.", "warning")
        return redirect(url_for("student.profile"))

    subject_id = request.form.get("subject_id", type=int)
    create_seven_day_revision_plan(current_user.id, branch.id, subject_id=subject_id)
    flash("7-day personalized revision plan created.", "success")
    return redirect(url_for("analytics.revision"))


@analytics_bp.route("/revision/task/<int:task_id>/toggle", methods=["POST"])
@role_required("student")
def toggle_revision_task(task_id: int):
    """Toggle completion status of a daily revision task."""
    task = (
        RevisionTask.query.join(RevisionTask.plan)
        .filter(RevisionTask.id == task_id, RevisionPlan.student_id == current_user.id)
        .first_or_404()
    )
    task.is_completed = not task.is_completed
    task.completed_at = datetime.now(timezone.utc) if task.is_completed else None
    db.session.commit()
    return redirect(url_for("analytics.revision"))


@analytics_bp.route("/revision/task/<int:task_id>/edit", methods=["POST"])
@role_required("student")
def edit_revision_task(task_id: int):
    """Allow students to customize a task title/description in their revision schedule."""
    task = (
        RevisionTask.query.join(RevisionTask.plan)
        .filter(RevisionTask.id == task_id, RevisionPlan.student_id == current_user.id)
        .first_or_404()
    )
    new_title = (request.form.get("title") or "").strip()
    if new_title:
        task.title = new_title
    task.description = (request.form.get("description") or "").strip()
    db.session.commit()
    flash("Revision task updated.", "success")
    return redirect(url_for("analytics.revision"))


@analytics_bp.route("/formulas")
@role_required("student")
def formulas():
    """Searchable GATE Formula & Shortcut Library."""
    ctx = _get_student_context()
    branch = ctx["selected_branch"]
    subject_id = request.args.get("subject_id", type=int)
    q_text = (request.args.get("q") or "").strip()

    query = FormulaEntry.query.options(joinedload(FormulaEntry.subject))
    if branch:
        query = query.filter_by(branch_id=branch.id)
    if subject_id:
        query = query.filter_by(subject_id=subject_id)
    if q_text:
        like_term = f"%{q_text}%"
        query = query.filter(
            FormulaEntry.title.ilike(like_term) | FormulaEntry.formula_latex.ilike(like_term)
        )

    items = query.order_by(FormulaEntry.id.asc()).all()
    subjects = (
        get_syllabus_tree(ctx["syllabus_version"].id) if ctx["syllabus_version"] else []
    )
    return render_template(
        "student/formulas.html",
        **ctx,
        formulas=items,
        subjects=subjects,
        selected_subject_id=subject_id,
        q_text=q_text,
    )
