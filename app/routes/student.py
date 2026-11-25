"""Student dashboard, branch selection, syllabus browser, and profile routes."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.models.attempt import Bookmark, ErrorNotebookEntry, Result, StudentAttempt
from app.models.syllabus import Branch
from app.services.auth_service import log_audit, role_required
from app.services.syllabus_service import (
    count_syllabus_nodes,
    get_active_branches,
    get_available_exam_years,
    get_exam_pattern,
    get_syllabus_tree,
    resolve_syllabus_version,
)

student_bp = Blueprint("student", __name__, url_prefix="/student")


def _get_student_context():
    """Return active branch, target year, syllabus version, and exam pattern for current student."""
    profile = current_user.student_profile
    branches = get_active_branches()
    branch = None
    if profile and profile.selected_branch_id:
        branch = Branch.query.filter_by(id=profile.selected_branch_id, is_active=True).first()
    if not branch and branches:
        branch = branches[0]
        if profile:
            profile.selected_branch_id = branch.id
            db.session.commit()

    exam_year = profile.target_exam_year if profile else 2026
    syllabus_version = resolve_syllabus_version(branch.id, exam_year) if branch else None
    exam_pattern = get_exam_pattern(branch.id, exam_year) if branch else None
    years = get_available_exam_years(branch.id if branch else None)
    return {
        "profile": profile,
        "branches": branches,
        "selected_branch": branch,
        "exam_year": exam_year,
        "years": years,
        "syllabus_version": syllabus_version,
        "exam_pattern": exam_pattern,
    }


@student_bp.route("/dashboard")
@role_required("student")
def dashboard():
    """Primary student workspace overview."""
    ctx = _get_student_context()
    syllabus_counts = (
        count_syllabus_nodes(ctx["syllabus_version"].id)
        if ctx["syllabus_version"]
        else {"subjects": 0, "chapters": 0, "topics": 0, "concepts": 0}
    )
    subjects = (
        get_syllabus_tree(ctx["syllabus_version"].id) if ctx["syllabus_version"] else []
    )
    completed_attempts = (
        StudentAttempt.query.filter(
            StudentAttempt.student_id == current_user.id,
            StudentAttempt.status.in_(["submitted", "auto_submitted"]),
        )
        .order_by(StudentAttempt.submitted_at.desc())
        .all()
    )
    results = [a.result for a in completed_attempts if a.result]
    attempts_count = len(completed_attempts)
    avg_accuracy = (
        round(sum(r.accuracy_percent for r in results) / len(results), 1)
        if results
        else None
    )
    best_score = (
        max(
            (
                round((r.total_marks_obtained / r.max_marks) * 100.0, 1)
                if r.max_marks > 0
                else 0.0
                for r in results
            ),
            default=None,
        )
    )
    unresolved_errors = ErrorNotebookEntry.query.filter_by(
        student_id=current_user.id, status="unresolved"
    ).count()
    bookmarks_count = Bookmark.query.filter_by(student_id=current_user.id).count()

    return render_template(
        "student/dashboard.html",
        **ctx,
        syllabus_counts=syllabus_counts,
        subjects=subjects,
        attempts_count=attempts_count,
        avg_accuracy=avg_accuracy,
        best_score=best_score,
        recent_attempts=completed_attempts[:5],
        unresolved_errors=unresolved_errors,
        bookmarks_count=bookmarks_count,
    )


@student_bp.route("/syllabus")
@role_required("student")
def syllabus():
    """Interactive syllabus hierarchy navigator (Branch -> Subject -> Chapter -> Topic -> Concept)."""
    ctx = _get_student_context()
    requested_branch_id = request.args.get("branch_id", type=int)
    requested_year = request.args.get("year", type=int)

    branch = (
        Branch.query.filter_by(id=requested_branch_id, is_active=True).first()
        if requested_branch_id
        else ctx["selected_branch"]
    )
    exam_year = requested_year or ctx["exam_year"]
    syllabus_version = resolve_syllabus_version(branch.id, exam_year) if branch else None
    subjects = get_syllabus_tree(syllabus_version.id) if syllabus_version else []
    counts = (
        count_syllabus_nodes(syllabus_version.id)
        if syllabus_version
        else {"subjects": 0, "chapters": 0, "topics": 0, "concepts": 0}
    )
    exam_pattern = get_exam_pattern(branch.id, exam_year) if branch else None

    return render_template(
        "student/syllabus.html",
        branches=ctx["branches"],
        selected_branch=branch,
        exam_year=exam_year,
        years=get_available_exam_years(branch.id if branch else None),
        syllabus_version=syllabus_version,
        subjects=subjects,
        syllabus_counts=counts,
        exam_pattern=exam_pattern,
    )


@student_bp.route("/profile", methods=["GET", "POST"])
@role_required("student")
def profile():
    """Manage student branch selection, target exam year, and account settings."""
    ctx = _get_student_context()
    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        branch_id = request.form.get("branch_id", type=int)
        exam_year = request.form.get("target_exam_year", type=int) or 2026
        study_minutes = request.form.get("daily_study_minutes", type=int) or 120

        if len(full_name) < 2:
            flash("Full name must be at least 2 characters.", "danger")
            return redirect(url_for("student.profile"))

        branch = Branch.query.filter_by(id=branch_id, is_active=True).first()
        if not branch:
            flash("Please select a valid GATE branch.", "danger")
            return redirect(url_for("student.profile"))

        current_user.full_name = full_name
        current_user.student_profile.selected_branch_id = branch.id
        current_user.student_profile.target_exam_year = exam_year
        current_user.student_profile.daily_study_minutes = max(15, min(720, study_minutes))

        log_audit(
            action="student.profile_update",
            entity_type="student_profile",
            entity_id=current_user.student_profile.id,
            details={"branch": branch.code, "target_exam_year": exam_year},
        )
        db.session.commit()
        flash("Branch and profile preferences updated.", "success")
        return redirect(url_for("student.dashboard"))

    return render_template("student/profile.html", **ctx)


@student_bp.route("/switch-branch", methods=["POST"])
@role_required("student")
def switch_branch():
    """Quick branch and target-year switcher from the student dashboard."""
    branch_id = request.form.get("branch_id", type=int)
    exam_year = request.form.get("target_exam_year", type=int)
    branch = Branch.query.filter_by(id=branch_id, is_active=True).first()
    if not branch:
        flash("Invalid branch selected.", "danger")
        return redirect(url_for("student.dashboard"))

    current_user.student_profile.selected_branch_id = branch.id
    if exam_year:
        current_user.student_profile.target_exam_year = exam_year
    log_audit(
        action="student.switch_branch",
        entity_type="student_profile",
        entity_id=current_user.student_profile.id,
        details={"branch": branch.code, "exam_year": current_user.student_profile.target_exam_year},
    )
    db.session.commit()
    flash(f"Switched active GATE branch to {branch.code} – {branch.name}.", "success")
    return redirect(request.referrer or url_for("student.dashboard"))


@student_bp.route("/module/<module_name>")
@role_required("student")
def upcoming_module(module_name: str):
    """Graceful status view for Phase 2/3/4 modules prior to activation."""
    allowed = {
        "assessments": ("Take a Test", "Phase 2 – Examination Engine"),
        "pyq": ("PYQ Practice", "Phase 2 – Examination Engine"),
        "ai-practice": ("AI Practice", "Phase 3 – AI Question Generation"),
        "mock-tests": ("Full Mock Tests", "Phase 2 – Examination Engine"),
        "performance": ("My Performance", "Phase 4 – Analytics & Readiness"),
        "advisor": ("AI Advisor", "Phase 4 – Personalized Recommendations"),
        "revision": ("My Revision", "Phase 4 – Revision Plans"),
        "error-notebook": ("Error Notebook", "Phase 2 / 4 – Mistake Tracking"),
        "bookmarks": ("Bookmarks", "Phase 2 – Question Bank"),
        "history": ("Test History", "Phase 2 – Examination Engine"),
        "readiness": ("GATE Readiness", "Phase 4 – Readiness Tracker"),
    }
    title, phase_label = allowed.get(module_name, ("Module", "Upcoming Phase"))
    ctx = _get_student_context()
    return render_template(
        "student/module_status.html",
        **ctx,
        module_title=title,
        phase_label=phase_label,
        module_name=module_name,
    )
