"""Administrator dashboard, branch/syllabus/pattern CRUD, student management, and audit logs."""

from datetime import date
import hashlib
from pathlib import Path

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

from app.extensions import db, limiter
from app.models.paper import (
    ExtractedQuestion,
    ExtractionJob,
    GenerationJob,
    Paper,
    PaperVersion,
)
from app.models.question import AnswerVerification, Question, QuestionHistory
from app.models.syllabus import (
    Branch,
    Chapter,
    Concept,
    ExamPattern,
    Subject,
    SyllabusVersion,
    Topic,
)
from app.models.system import AuditLog
from app.models.user import User
from app.services.analytics_service import get_platform_analytics
from app.services.auth_service import log_audit, role_required
from app.services.llm_client import is_llm_configured
from app.services.question_service import query_question_bank
from app.services.syllabus_service import count_syllabus_nodes, get_syllabus_tree, resolve_syllabus_version

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/overview")
@role_required("admin")
def overview():
    """Admin operational overview dashboard."""
    branches = Branch.query.order_by(Branch.code.asc()).all()
    syllabus_versions = SyllabusVersion.query.order_by(
        SyllabusVersion.exam_year.desc(), SyllabusVersion.branch_id.asc()
    ).all()
    patterns_count = ExamPattern.query.count()
    students_count = (
        User.query.join(User.role).filter_by(name="student").count()
    )
    questions_count = Question.query.count()
    recent_logs = (
        AuditLog.query.order_by(AuditLog.created_at.desc()).limit(12).all()
    )
    return render_template(
        "admin/overview.html",
        branches=branches,
        syllabus_versions=syllabus_versions,
        patterns_count=patterns_count,
        students_count=students_count,
        questions_count=questions_count,
        recent_logs=recent_logs,
    )


@admin_bp.route("/branches", methods=["GET", "POST"])
@role_required("admin")
def branches():
    """View, create, and toggle GATE branches."""
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "toggle":
            branch_id = request.form.get("branch_id", type=int)
            branch = Branch.query.get_or_404(branch_id)
            branch.is_active = not branch.is_active
            log_audit("admin.branch_toggle", "branch", branch.id, {"is_active": branch.is_active})
            db.session.commit()
            flash(f"Branch {branch.code} status updated.", "success")
            return redirect(url_for("admin.branches"))

        code = (request.form.get("code") or "").strip().upper()
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        if not code or not name:
            flash("Branch code and name are required.", "danger")
            return redirect(url_for("admin.branches"))
        if Branch.query.filter_by(code=code).first():
            flash(f"Branch code '{code}' already exists.", "warning")
            return redirect(url_for("admin.branches"))

        branch = Branch(code=code, name=name, description=description, is_active=True)
        db.session.add(branch)
        db.session.flush()
        log_audit("admin.branch_create", "branch", branch.id, {"code": code, "name": name})
        db.session.commit()
        flash(f"Created branch {code} – {name}.", "success")
        return redirect(url_for("admin.branches"))

    all_branches = Branch.query.order_by(Branch.code.asc()).all()
    return render_template("admin/branches.html", branches=all_branches)


@admin_bp.route("/syllabus", methods=["GET", "POST"])
@role_required("admin")
def syllabus():
    """Manage syllabus versions and browse/add Subject -> Chapter -> Topic -> Concept nodes."""
    branches = Branch.query.order_by(Branch.code.asc()).all()
    versions = SyllabusVersion.query.order_by(
        SyllabusVersion.exam_year.desc(), SyllabusVersion.branch_id.asc()
    ).all()

    if request.method == "POST":
        form_type = request.form.get("form_type")
        if form_type == "create_version":
            branch_id = request.form.get("branch_id", type=int)
            exam_year = request.form.get("exam_year", type=int)
            version_label = (request.form.get("version_label") or "Official v1.0").strip()
            syllabus_source = (request.form.get("syllabus_source") or "").strip()
            effective_str = request.form.get("effective_date") or ""
            status = request.form.get("status") or "active"
            try:
                eff_date = date.fromisoformat(effective_str) if effective_str else date.today()
            except ValueError:
                eff_date = date.today()

            if not branch_id or not exam_year or not syllabus_source:
                flash("Branch, examination year, and syllabus source are required.", "danger")
                return redirect(url_for("admin.syllabus"))

            sv = SyllabusVersion(
                branch_id=branch_id,
                exam_year=exam_year,
                version_label=version_label,
                syllabus_source=syllabus_source,
                effective_date=eff_date,
                status=status,
            )
            db.session.add(sv)
            db.session.flush()
            log_audit(
                "admin.syllabus_version_create",
                "syllabus_version",
                sv.id,
                {"branch_id": branch_id, "exam_year": exam_year},
            )
            db.session.commit()
            flash("Syllabus version created.", "success")
            return redirect(url_for("admin.syllabus", version_id=sv.id))

        if form_type == "add_subject":
            version_id = request.form.get("syllabus_version_id", type=int)
            code = (request.form.get("code") or "").strip().upper()
            name = (request.form.get("name") or "").strip()
            is_ga = bool(request.form.get("is_general_aptitude"))
            if version_id and code and name:
                order = Subject.query.filter_by(syllabus_version_id=version_id).count() + 1
                subj = Subject(
                    syllabus_version_id=version_id,
                    code=code,
                    name=name,
                    display_order=order,
                    is_general_aptitude=is_ga,
                )
                db.session.add(subj)
                db.session.flush()
                log_audit("admin.subject_create", "subject", subj.id, {"name": name})
                db.session.commit()
                flash(f"Added subject '{name}'.", "success")
            return redirect(url_for("admin.syllabus", version_id=version_id))

        if form_type == "add_chapter":
            version_id = request.form.get("version_id", type=int)
            subject_id = request.form.get("subject_id", type=int)
            name = (request.form.get("name") or "").strip()
            if subject_id and name:
                order = Chapter.query.filter_by(subject_id=subject_id).count() + 1
                ch = Chapter(subject_id=subject_id, name=name, display_order=order)
                db.session.add(ch)
                db.session.flush()
                log_audit("admin.chapter_create", "chapter", ch.id, {"name": name})
                db.session.commit()
                flash(f"Added chapter '{name}'.", "success")
            return redirect(url_for("admin.syllabus", version_id=version_id))

        if form_type == "add_topic":
            version_id = request.form.get("version_id", type=int)
            chapter_id = request.form.get("chapter_id", type=int)
            name = (request.form.get("name") or "").strip()
            if chapter_id and name:
                order = Topic.query.filter_by(chapter_id=chapter_id).count() + 1
                tp = Topic(chapter_id=chapter_id, name=name, display_order=order)
                db.session.add(tp)
                db.session.flush()
                log_audit("admin.topic_create", "topic", tp.id, {"name": name})
                db.session.commit()
                flash(f"Added topic '{name}'.", "success")
            return redirect(url_for("admin.syllabus", version_id=version_id))

        if form_type == "add_concept":
            version_id = request.form.get("version_id", type=int)
            topic_id = request.form.get("topic_id", type=int)
            name = (request.form.get("name") or "").strip()
            if topic_id and name:
                order = Concept.query.filter_by(topic_id=topic_id).count() + 1
                cp = Concept(topic_id=topic_id, name=name, display_order=order)
                db.session.add(cp)
                db.session.flush()
                log_audit("admin.concept_create", "concept", cp.id, {"name": name})
                db.session.commit()
                flash(f"Added concept '{name}'.", "success")
            return redirect(url_for("admin.syllabus", version_id=version_id))

    selected_version_id = request.args.get("version_id", type=int)
    selected_version = (
        SyllabusVersion.query.get(selected_version_id)
        if selected_version_id
        else (versions[0] if versions else None)
    )
    subjects = get_syllabus_tree(selected_version.id) if selected_version else []
    counts = (
        count_syllabus_nodes(selected_version.id)
        if selected_version
        else {"subjects": 0, "chapters": 0, "topics": 0, "concepts": 0}
    )

    return render_template(
        "admin/syllabus.html",
        branches=branches,
        versions=versions,
        selected_version=selected_version,
        subjects=subjects,
        counts=counts,
    )


@admin_bp.route("/exam-patterns", methods=["GET", "POST"])
@role_required("admin")
def exam_patterns():
    """Manage official GATE examination patterns by branch and year."""
    branches = Branch.query.order_by(Branch.code.asc()).all()
    if request.method == "POST":
        branch_id = request.form.get("branch_id", type=int)
        exam_year = request.form.get("exam_year", type=int)
        duration_minutes = request.form.get("duration_minutes", type=int) or 180
        total_marks = request.form.get("total_marks", type=int) or 100
        total_questions = request.form.get("total_questions", type=int) or 65
        ga_marks = request.form.get("ga_marks", type=int) or 15
        technical_marks = request.form.get("technical_marks", type=int) or 85

        existing = ExamPattern.query.filter_by(branch_id=branch_id, exam_year=exam_year).first()
        if existing:
            existing.duration_minutes = duration_minutes
            existing.total_marks = total_marks
            existing.total_questions = total_questions
            existing.ga_marks = ga_marks
            existing.technical_marks = technical_marks
            log_audit("admin.pattern_update", "exam_pattern", existing.id)
            flash("Exam pattern updated.", "success")
        else:
            pattern = ExamPattern(
                branch_id=branch_id,
                exam_year=exam_year,
                duration_minutes=duration_minutes,
                total_marks=total_marks,
                total_questions=total_questions,
                ga_marks=ga_marks,
                technical_marks=technical_marks,
                rules_json={
                    "negative_marking": {"MCQ_1": -1 / 3, "MCQ_2": -2 / 3, "MSQ": 0, "NAT": 0},
                    "ga_questions": {"1_mark": 5, "2_mark": 5},
                    "tech_questions": {"1_mark": 25, "2_mark": 30},
                },
            )
            db.session.add(pattern)
            db.session.flush()
            log_audit("admin.pattern_create", "exam_pattern", pattern.id)
            flash("Exam pattern created.", "success")
        db.session.commit()
        return redirect(url_for("admin.exam_patterns"))

    patterns = (
        ExamPattern.query.join(ExamPattern.branch)
        .order_by(ExamPattern.exam_year.desc(), Branch.code.asc())
        .all()
    )
    return render_template("admin/exam_patterns.html", branches=branches, patterns=patterns)


@admin_bp.route("/students", methods=["GET", "POST"])
@role_required("admin")
def students():
    """View registered students and toggle active status."""
    if request.method == "POST":
        user_id = request.form.get("user_id", type=int)
        target = User.query.get_or_404(user_id)
        if target.id == current_user.id or target.is_admin:
            flash("Cannot modify administrator status from student management.", "warning")
            return redirect(url_for("admin.students"))
        target.is_active = not target.is_active
        log_audit(
            "admin.student_status_toggle",
            "user",
            target.id,
            {"is_active": target.is_active},
        )
        db.session.commit()
        flash(f"Updated status for {target.email}.", "success")
        return redirect(url_for("admin.students"))

    student_users = (
        User.query.join(User.role)
        .filter_by(name="student")
        .order_by(User.created_at.desc())
        .all()
    )
    return render_template("admin/students.html", students=student_users)


@admin_bp.route("/logs")
@role_required("admin")
def logs():
    """System audit log viewer."""
    page = request.args.get("page", 1, type=int)
    pagination = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=25, error_out=False
    )
    return render_template("admin/logs.html", pagination=pagination)


@admin_bp.route("/question-bank", methods=["GET", "POST"])
@role_required("admin")
def question_bank():
    """Browse, filter, and toggle publish status for questions in the central bank."""
    if request.method == "POST":
        q_id = request.form.get("question_id", type=int)
        action = request.form.get("action")
        q = Question.query.get_or_404(q_id)
        if action == "toggle_publish":
            q.is_published = not q.is_published
            log_audit("admin.question_publish_toggle", "question", q.id, {"is_published": q.is_published})
            db.session.commit()
            flash(f"Question #{q.id} publish status updated.", "success")
        return redirect(request.referrer or url_for("admin.question_bank"))

    branch_id = request.args.get("branch_id", type=int)
    source_type = request.args.get("source_type", "ALL")
    question_type = request.args.get("question_type", "ALL")
    page = request.args.get("page", 1, type=int)

    branches = Branch.query.order_by(Branch.code.asc()).all()
    pagination = query_question_bank(
        branch_id=branch_id,
        source_type=source_type,
        question_type=question_type,
        published_only=False,
        page=page,
        per_page=15,
    )
    return render_template(
        "admin/question_bank.html",
        branches=branches,
        pagination=pagination,
        filters={"branch_id": branch_id, "source_type": source_type, "question_type": question_type},
    )


@admin_bp.route("/upload-paper", methods=["GET", "POST"])
@role_required("admin")
def upload_paper():
    """Upload a GATE question-paper PDF and trigger the automatic extraction pipeline."""
    branches = Branch.query.order_by(Branch.code.asc()).all()
    if request.method == "POST":
        pdf_file = request.files.get("pdf_file")
        branch_id = request.form.get("branch_id", type=int)
        exam_year = request.form.get("exam_year", type=int) or 2025
        shift = (request.form.get("shift") or "").strip() or None
        title = (request.form.get("title") or "").strip()

        if not pdf_file or not pdf_file.filename:
            flash("Please choose a PDF file to upload.", "danger")
            return redirect(url_for("admin.upload_paper"))

        filename = secure_filename(pdf_file.filename)
        if not filename.lower().endswith(".pdf"):
            flash("Only PDF files are accepted.", "danger")
            return redirect(url_for("admin.upload_paper"))

        raw_bytes = pdf_file.read()
        if not raw_bytes.startswith(b"%PDF"):
            flash("Invalid PDF signature. Please upload a valid PDF document.", "danger")
            return redirect(url_for("admin.upload_paper"))

        branch = Branch.query.get(branch_id)
        if not branch:
            flash("Please select a valid GATE branch.", "danger")
            return redirect(url_for("admin.upload_paper"))

        file_hash = hashlib.sha256(raw_bytes).hexdigest()
        upload_dir = Path(current_app.config["UPLOAD_FOLDER"]) / "papers"
        upload_dir.mkdir(parents=True, exist_ok=True)
        saved_name = f"{branch.code}_{exam_year}_{file_hash[:10]}_{filename}"
        abs_path = upload_dir / saved_name
        abs_path.write_bytes(raw_bytes)

        static_root = Path(current_app.root_path) / "static"
        rel_path = abs_path.relative_to(static_root).as_posix()

        paper = Paper(
            branch_id=branch.id,
            exam_year=exam_year,
            shift=shift,
            title=title or f"GATE {exam_year} {branch.code} Question Paper",
            uploaded_by_user_id=current_user.id,
        )
        db.session.add(paper)
        db.session.flush()

        pv = PaperVersion(
            paper_id=paper.id,
            file_path=rel_path,
            file_hash=file_hash,
            file_size_bytes=len(raw_bytes),
        )
        db.session.add(pv)
        db.session.flush()

        job = ExtractionJob(paper_version_id=pv.id, status="uploaded", progress_percent=5)
        db.session.add(job)
        db.session.flush()

        log_audit(
            "admin.paper_upload",
            "extraction_job",
            job.id,
            {"branch": branch.code, "exam_year": exam_year, "filename": saved_name},
        )
        db.session.commit()

        from worker.tasks import enqueue_paper_job

        enqueue_paper_job(
            current_app._get_current_object(),
            job.id,
            run_async=(not current_app.config.get("TESTING")),
        )
        flash("PDF uploaded. Automatic extraction pipeline started.", "success")
        return redirect(url_for("admin.job_detail", job_id=job.id))

    recent_jobs = (
        ExtractionJob.query.options(joinedload(ExtractionJob.paper_version).joinedload(PaperVersion.paper))
        .order_by(ExtractionJob.id.desc())
        .limit(8)
        .all()
    )
    return render_template("admin/upload_paper.html", branches=branches, recent_jobs=recent_jobs)


@admin_bp.route("/jobs")
@role_required("admin")
def jobs():
    """List all PDF paper extraction jobs and their status."""
    all_jobs = (
        ExtractionJob.query.options(
            joinedload(ExtractionJob.paper_version).joinedload(PaperVersion.paper).joinedload(Paper.branch)
        )
        .order_by(ExtractionJob.id.desc())
        .all()
    )
    return render_template("admin/jobs.html", jobs=all_jobs)


@admin_bp.route("/jobs/<int:job_id>")
@role_required("admin")
def job_detail(job_id: int):
    """Detailed monitor for an extraction job's pipeline logs and segmented questions."""
    job = (
        ExtractionJob.query.options(
            joinedload(ExtractionJob.paper_version).joinedload(PaperVersion.paper).joinedload(Paper.branch),
            joinedload(ExtractionJob.logs),
            joinedload(ExtractionJob.extracted_questions),
        )
        .filter_by(id=job_id)
        .first_or_404()
    )
    return render_template("admin/job_detail.html", job=job)


@admin_bp.route("/jobs/<int:job_id>/status")
@role_required("admin")
def job_status_api(job_id: int):
    """Polling JSON endpoint for live extraction job progress."""
    job = ExtractionJob.query.get_or_404(job_id)
    return jsonify(
        {
            "id": job.id,
            "status": job.status,
            "progress_percent": job.progress_percent,
            "total_detected": job.total_detected,
            "published_count": job.published_count,
            "review_count": job.review_count,
            "failed_count": job.failed_count,
            "error_message": job.error_message,
        }
    )


@admin_bp.route("/verification", methods=["GET", "POST"])
@role_required("admin")
def verification():
    """Exception review queue for questions awaiting verification or manual answer review."""
    if request.method == "POST":
        q_id = request.form.get("question_id", type=int)
        action = request.form.get("action")
        q = Question.query.get_or_404(q_id)

        if action == "approve_publish":
            override_answer = (request.form.get("override_answer") or "").strip()
            if override_answer:
                if q.question_type == "MCQ":
                    q.correct_answer_json = {"option": override_answer.upper()[:1]}
                    for opt in q.options:
                        opt.is_correct = opt.label == q.correct_answer_json["option"]
                elif q.question_type == "MSQ":
                    chosen = sorted({x.strip().upper()[:1] for x in override_answer.split(",") if x.strip()})
                    q.correct_answer_json = {"options": chosen}
                    for opt in q.options:
                        opt.is_correct = opt.label in chosen
                elif q.question_type == "NAT":
                    val = float(override_answer)
                    q.correct_answer_json = {"value": val}
                    q.nat_min = val - 0.01
                    q.nat_max = val + 0.01

            q.verification_status = "verified"
            q.is_published = True
            db.session.add(
                AnswerVerification(
                    question_id=q.id,
                    verifier_type="human_admin",
                    model_or_tool=current_user.email,
                    proposed_answer_json=q.correct_answer_json,
                    is_match=True,
                    confidence_score=1.0,
                    notes="Approved and verified by administrator.",
                    verified_by_user_id=current_user.id,
                )
            )
            db.session.add(
                QuestionHistory(
                    question_id=q.id,
                    changed_by_user_id=current_user.id,
                    change_type="admin_verify_publish",
                    diff_json={"correct_answer": q.correct_answer_json},
                )
            )
            log_audit("admin.question_verified", "question", q.id)
            db.session.commit()
            flash(f"Question #{q.id} verified and published.", "success")
        elif action == "reject":
            q.is_published = False
            q.verification_status = "needs_manual_review"
            log_audit("admin.question_rejected", "question", q.id)
            db.session.commit()
            flash(f"Question #{q.id} kept unpublished.", "info")

        return redirect(url_for("admin.verification"))

    pending_questions = (
        Question.query.options(
            joinedload(Question.branch),
            joinedload(Question.subject),
            joinedload(Question.source),
            joinedload(Question.options),
            joinedload(Question.images),
            joinedload(Question.verifications),
        )
        .filter(Question.verification_status != "verified")
        .order_by(Question.id.desc())
        .all()
    )
    return render_template("admin/verification.html", pending_questions=pending_questions)


@admin_bp.route("/ai-generation", methods=["GET", "POST"])
@role_required("admin")
@limiter.limit("10 per minute")
def ai_generation():
    """Request and monitor original syllabus-aligned AI question generation jobs."""
    branches = Branch.query.order_by(Branch.code.asc()).all()
    if request.method == "POST":
        branch_id = request.form.get("branch_id", type=int)
        subject_id = request.form.get("subject_id", type=int)
        target_count = max(1, min(15, request.form.get("target_count", type=int) or 3))

        job = GenerationJob(
            requested_by_user_id=current_user.id,
            branch_id=branch_id,
            subject_id=subject_id,
            target_count=target_count,
            status="queued",
        )
        db.session.add(job)
        db.session.flush()
        log_audit("admin.ai_generation_start", "generation_job", job.id, {"count": target_count})
        db.session.commit()

        from worker.tasks import enqueue_generation_job

        enqueue_generation_job(
            current_app._get_current_object(),
            job.id,
            run_async=(not current_app.config.get("TESTING")),
        )
        flash("AI question generation job queued.", "success")
        return redirect(url_for("admin.ai_generation"))

    selected_branch_id = request.args.get("branch_id", type=int) or (branches[0].id if branches else None)
    sv = resolve_syllabus_version(selected_branch_id, 2026) if selected_branch_id else None
    subjects = get_syllabus_tree(sv.id) if sv else []
    gen_jobs = (
        GenerationJob.query.options(joinedload(GenerationJob.branch), joinedload(GenerationJob.subject), joinedload(GenerationJob.logs))
        .order_by(GenerationJob.id.desc())
        .limit(15)
        .all()
    )
    return render_template(
        "admin/ai_generation.html",
        branches=branches,
        selected_branch_id=selected_branch_id,
        subjects=subjects,
        gen_jobs=gen_jobs,
        llm_configured=is_llm_configured(),
    )


@admin_bp.route("/analytics")
@role_required("admin")
def analytics():
    """Platform-wide question bank and student assessment analytics."""
    metrics = get_platform_analytics()
    return render_template("admin/analytics.html", metrics=metrics)


@admin_bp.route("/module/<module_name>")
@role_required("admin")
def upcoming_module(module_name: str):
    """Graceful status view for Phase 2/3/4 admin modules prior to activation."""
    allowed = {
        "upload-paper": ("Question Paper Upload", "Phase 3 – PDF Extraction Pipeline"),
        "jobs": ("Processing Jobs", "Phase 3 – Background PDF Worker"),
        "question-bank": ("Question Bank", "Phase 2 – Historical & Generated Questions"),
        "ai-generation": ("AI Question Generation", "Phase 3 – AI Question Generator"),
        "verification": ("Answer Verification", "Phase 3 – Independent Verifier"),
        "analytics": ("Platform Analytics", "Phase 4 – System Analytics"),
        "settings": ("Settings", "Phase 3 / 4 – Runtime Settings"),
    }
    title, phase_label = allowed.get(module_name, ("Admin Module", "Upcoming Phase"))
    return render_template(
        "admin/module_status.html",
        module_title=title,
        phase_label=phase_label,
        module_name=module_name,
    )
