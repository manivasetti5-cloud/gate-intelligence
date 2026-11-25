"""Authentication, RBAC, and audit logging helpers."""

from functools import wraps
from typing import Callable

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.system import AuditLog
from app.models.user import AdminProfile, Role, StudentProfile, User, utcnow


def log_audit(
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    details: dict | None = None,
    actor_user_id: int | None = None,
) -> None:
    """Persist an immutable audit log entry."""
    uid = actor_user_id
    if uid is None and current_user and getattr(current_user, "is_authenticated", False):
        uid = current_user.id
    entry = AuditLog(
        actor_user_id=uid,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details_json=details or {},
        ip_address=request.remote_addr if request else None,
    )
    db.session.add(entry)


def role_required(role_name: str) -> Callable:
    """Restrict route access to authenticated users holding the specified role."""

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.is_active:
                abort(403)
            if current_user.role_name != role_name:
                if request.path.startswith("/api/"):
                    abort(403)
                flash("You do not have permission to access that section.", "danger")
                if current_user.is_admin:
                    return redirect(url_for("admin.overview"))
                return redirect(url_for("student.dashboard"))
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def ensure_default_roles() -> dict[str, Role]:
    """Ensure 'student' and 'admin' roles exist in the database."""
    roles: dict[str, Role] = {}
    for name, desc in (
        ("student", "GATE aspirant taking assessments and tracking preparation"),
        ("admin", "Platform administrator managing papers, syllabi, and verification"),
    ):
        role = Role.query.filter_by(name=name).first()
        if not role:
            role = Role(name=name, description=desc)
            db.session.add(role)
            db.session.flush()
        roles[name] = role
    return roles


def register_student(
    email: str,
    full_name: str,
    password: str,
    branch_id: int | None = None,
    target_exam_year: int = 2026,
) -> User:
    """Create a new student account and associated StudentProfile."""
    roles = ensure_default_roles()
    user = User(
        email=email.strip().lower(),
        full_name=full_name.strip(),
        role_id=roles["student"].id,
        is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    profile = StudentProfile(
        user_id=user.id,
        selected_branch_id=branch_id,
        target_exam_year=target_exam_year,
    )
    db.session.add(profile)
    log_audit(
        action="student.register",
        entity_type="user",
        entity_id=user.id,
        details={"email": user.email, "target_exam_year": target_exam_year},
        actor_user_id=user.id,
    )
    db.session.commit()
    return user


def create_admin_user(
    email: str,
    full_name: str,
    password: str,
    department: str = "Platform Operations",
) -> User:
    """Create an administrator account if one does not already exist."""
    roles = ensure_default_roles()
    existing = User.query.filter_by(email=email.strip().lower()).first()
    if existing:
        return existing

    user = User(
        email=email.strip().lower(),
        full_name=full_name.strip(),
        role_id=roles["admin"].id,
        is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    profile = AdminProfile(
        user_id=user.id,
        department=department,
        permissions_json={"manage_papers": True, "manage_syllabus": True, "manage_users": True},
    )
    db.session.add(profile)
    log_audit(
        action="admin.seed",
        entity_type="user",
        entity_id=user.id,
        details={"email": user.email},
        actor_user_id=user.id,
    )
    db.session.commit()
    return user


def record_login(user: User) -> None:
    """Update last_login_at and record audit event."""
    user.last_login_at = utcnow()
    log_audit(
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        details={"role": user.role_name},
        actor_user_id=user.id,
    )
    db.session.commit()
