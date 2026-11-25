"""Authentication routes for students and administrators."""

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import text

from app.extensions import db, limiter
from app.models.user import User
from app.services.auth_service import log_audit, record_login, register_student
from app.services.syllabus_service import get_active_branches, get_available_exam_years

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/health")
def health():
    """Cloud platform health check verifying database connectivity."""
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ok", "database": "connected"}), 200
    except Exception as exc:
        return jsonify({"status": "error", "database": str(exc)}), 503


@auth_bp.route("/")
def index():
    """Redirect authenticated users to their role dashboard or show landing page."""
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin.overview"))
        return redirect(url_for("student.dashboard"))
    branches = get_active_branches()
    return render_template("auth/landing.html", branches=branches)


@auth_bp.route("/auth/login", methods=["GET", "POST"])
@limiter.limit("20 per minute")
def login():
    """Student login page."""
    if current_user.is_authenticated:
        return redirect(url_for("admin.overview" if current_user.is_admin else "student.dashboard"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html", email=email), 401

        if not user.is_active:
            flash("Your account has been deactivated. Contact an administrator.", "danger")
            return render_template("auth/login.html", email=email), 403

        if user.is_admin:
            flash("Administrators must sign in through the Admin Portal.", "warning")
            return redirect(url_for("auth.admin_login"))

        login_user(user, remember=remember)
        record_login(user)
        next_url = request.args.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("student.dashboard"))

    return render_template("auth/login.html")


@auth_bp.route("/auth/admin/login", methods=["GET", "POST"])
@limiter.limit("15 per minute")
def admin_login():
    """Dedicated administrator login portal."""
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin.overview"))
        return redirect(url_for("student.dashboard"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password) or not user.is_admin:
            log_audit(
                action="auth.admin_login_failed",
                entity_type="user",
                entity_id=email,
                details={"reason": "invalid_credentials_or_role"},
            )
            from app.extensions import db

            db.session.commit()
            flash("Invalid administrator credentials.", "danger")
            return render_template("auth/admin_login.html", email=email), 401

        if not user.is_active:
            flash("Administrator account is inactive.", "danger")
            return render_template("auth/admin_login.html", email=email), 403

        login_user(user, remember=False)
        record_login(user)
        return redirect(url_for("admin.overview"))

    return render_template("auth/admin_login.html")


@auth_bp.route("/auth/register", methods=["GET", "POST"])
@limiter.limit("15 per minute")
def register():
    """Student registration flow with initial branch and exam year selection."""
    if current_user.is_authenticated:
        return redirect(url_for("student.dashboard"))

    branches = get_active_branches()
    years = get_available_exam_years()

    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""
        branch_id_raw = request.form.get("branch_id")
        exam_year_raw = request.form.get("target_exam_year") or "2026"

        errors: list[str] = []
        if len(full_name) < 2:
            errors.append("Full name must be at least 2 characters.")
        if "@" not in email or "." not in email.split("@")[-1]:
            errors.append("Please enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        if password != confirm_password:
            errors.append("Passwords do not match.")
        if User.query.filter_by(email=email).first():
            errors.append("An account with this email already exists.")

        branch_id = int(branch_id_raw) if branch_id_raw and branch_id_raw.isdigit() else None
        if not branch_id and branches:
            branch_id = branches[0].id
        try:
            exam_year = int(exam_year_raw)
        except ValueError:
            exam_year = 2026

        if errors:
            for msg in errors:
                flash(msg, "danger")
            return (
                render_template(
                    "auth/register.html",
                    branches=branches,
                    years=years,
                    form_data=request.form,
                ),
                400,
            )

        user = register_student(
            email=email,
            full_name=full_name,
            password=password,
            branch_id=branch_id,
            target_exam_year=exam_year,
        )
        login_user(user)
        record_login(user)
        flash("Welcome to GATE Intelligence! Your profile is ready.", "success")
        return redirect(url_for("student.dashboard"))

    return render_template("auth/register.html", branches=branches, years=years, form_data={})


@auth_bp.route("/auth/logout", methods=["POST"])
@login_required
def logout():
    """Log out current user cleanly via POST (CSRF-protected)."""
    is_admin = current_user.is_admin
    log_audit(
        action="auth.logout",
        entity_type="user",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
    )
    from app.extensions import db

    db.session.commit()
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.admin_login" if is_admin else "auth.login"))
