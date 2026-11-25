"""Student Question Bank browser, Bookmarks, and Error Notebook routes."""

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.attempt import Bookmark, ErrorNotebookEntry
from app.models.question import Question
from app.routes.student import _get_student_context
from app.services.auth_service import role_required
from app.services.question_service import query_question_bank
from app.services.syllabus_service import get_syllabus_tree

questions_bp = Blueprint("questions", __name__, url_prefix="/questions")


@questions_bp.route("/bank")
@role_required("student")
def bank():
    """Searchable, paginated Question Bank showing PYQs, AI-generated, and Sample Practice items."""
    ctx = _get_student_context()
    branch = ctx["selected_branch"]
    subject_id = request.args.get("subject_id", type=int)
    source_type = request.args.get("source_type", "ALL")
    question_type = request.args.get("question_type", "ALL")
    difficulty = request.args.get("difficulty", "mixed")
    search = request.args.get("q", "")
    page = request.args.get("page", 1, type=int)

    pagination = query_question_bank(
        branch_id=branch.id if branch else None,
        subject_id=subject_id,
        source_type=source_type,
        question_type=question_type,
        difficulty=difficulty,
        search=search,
        published_only=True,
        page=page,
        per_page=12,
    )
    subjects = (
        get_syllabus_tree(ctx["syllabus_version"].id) if ctx["syllabus_version"] else []
    )
    bookmarked_ids = {
        b.question_id for b in Bookmark.query.filter_by(student_id=current_user.id).all()
    }
    return render_template(
        "student/question_bank.html",
        **ctx,
        pagination=pagination,
        subjects=subjects,
        bookmarked_ids=bookmarked_ids,
        filters={
            "subject_id": subject_id,
            "source_type": source_type,
            "question_type": question_type,
            "difficulty": difficulty,
            "q": search,
        },
    )


@questions_bp.route("/<int:question_id>/bookmark", methods=["POST"])
@role_required("student")
def toggle_bookmark(question_id: int):
    """Toggle bookmark on a question for the logged-in student."""
    Question.query.get_or_404(question_id)
    existing = Bookmark.query.filter_by(
        student_id=current_user.id, question_id=question_id
    ).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        bookmarked = False
    else:
        db.session.add(Bookmark(student_id=current_user.id, question_id=question_id))
        db.session.commit()
        bookmarked = True

    if request.is_json:
        return jsonify({"bookmarked": bookmarked})
    flash("Bookmark updated.", "success")
    return redirect(request.referrer or url_for("questions.bookmarks"))


@questions_bp.route("/bookmarks")
@role_required("student")
def bookmarks():
    """List student's bookmarked questions."""
    ctx = _get_student_context()
    items = (
        Bookmark.query.options(
            joinedload(Bookmark.question).joinedload(Question.subject),
            joinedload(Bookmark.question).joinedload(Question.topic),
            joinedload(Bookmark.question).joinedload(Question.source),
            joinedload(Bookmark.question).joinedload(Question.options),
        )
        .filter_by(student_id=current_user.id)
        .order_by(Bookmark.created_at.desc())
        .all()
    )
    return render_template("student/bookmarks.html", **ctx, bookmarks=items)


@questions_bp.route("/error-notebook")
@role_required("student")
def error_notebook():
    """List incorrectly answered questions grouped by subject for targeted revision and reattempt."""
    ctx = _get_student_context()
    status_filter = request.args.get("status", "unresolved")
    q = ErrorNotebookEntry.query.options(
        joinedload(ErrorNotebookEntry.question).joinedload(Question.subject),
        joinedload(ErrorNotebookEntry.question).joinedload(Question.chapter),
        joinedload(ErrorNotebookEntry.question).joinedload(Question.concept),
        joinedload(ErrorNotebookEntry.question).joinedload(Question.source),
        joinedload(ErrorNotebookEntry.question).joinedload(Question.options),
    ).filter_by(student_id=current_user.id)

    if status_filter != "all":
        q = q.filter_by(status=status_filter)

    entries = q.order_by(ErrorNotebookEntry.updated_at.desc()).all()
    grouped: dict[str, list[ErrorNotebookEntry]] = {}
    for entry in entries:
        subj_name = entry.question.subject.name if entry.question and entry.question.subject else "General"
        grouped.setdefault(subj_name, []).append(entry)

    return render_template(
        "student/error_notebook.html",
        **ctx,
        entries=entries,
        grouped=grouped,
        status_filter=status_filter,
    )


@questions_bp.route("/error-notebook/<int:entry_id>/note", methods=["POST"])
@role_required("student")
def update_error_note(entry_id: int):
    """Save student's personal revision note or mark an error entry as mastered."""
    entry = ErrorNotebookEntry.query.filter_by(
        id=entry_id, student_id=current_user.id
    ).first_or_404()
    entry.personal_note = (request.form.get("personal_note") or "").strip()
    new_status = request.form.get("status")
    if new_status in ("unresolved", "reattempted_correct", "mastered"):
        entry.status = new_status
    db.session.commit()
    flash("Error notebook entry updated.", "success")
    return redirect(url_for("questions.error_notebook"))
