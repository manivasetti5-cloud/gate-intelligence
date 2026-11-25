"""Phase 1 tests: authentication, RBAC, branch selection, syllabus hierarchy, and dashboards."""

from app.models.syllabus import Branch, ExamPattern, SyllabusVersion
from app.models.user import User


def test_seeds_create_five_branches_and_patterns(client, app):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.get_json()["status"] == "ok"

    with app.app_context():
        branches = Branch.query.order_by(Branch.code.asc()).all()
        assert [b.code for b in branches] == ["CS", "DA", "EC", "EE", "ME"]
        assert SyllabusVersion.query.count() >= 5
        assert ExamPattern.query.count() >= 5


def test_student_registration_login_and_rbac(client, app):
    with app.app_context():
        cs_branch = Branch.query.filter_by(code="CS").first()
        cs_id = cs_branch.id

    resp = client.post(
        "/auth/register",
        data={
            "full_name": "Aarav Sharma",
            "email": "aarav@example.com",
            "branch_id": str(cs_id),
            "target_exam_year": "2026",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Welcome, Aarav Sharma" in resp.data
    assert b"CS" in resp.data

    # Student must NOT be able to access admin overview
    admin_resp = client.get("/admin/overview", follow_redirects=False)
    assert admin_resp.status_code == 302
    assert "/student/dashboard" in admin_resp.headers["Location"]

    # Student can explore syllabus
    syl_resp = client.get("/student/syllabus")
    assert syl_resp.status_code == 200
    assert b"Operating System" in syl_resp.data

    # Logout and login again
    client.post("/auth/logout", follow_redirects=True)
    login_resp = client.post(
        "/auth/login",
        data={"email": "aarav@example.com", "password": "Password123!"},
        follow_redirects=True,
    )
    assert login_resp.status_code == 200
    assert b"Welcome, Aarav Sharma" in login_resp.data


def test_student_branch_switch(client, app):
    with app.app_context():
        cs_id = Branch.query.filter_by(code="CS").first().id
        da_id = Branch.query.filter_by(code="DA").first().id

    client.post(
        "/auth/register",
        data={
            "full_name": "Priya Nair",
            "email": "priya@example.com",
            "branch_id": str(cs_id),
            "target_exam_year": "2026",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
        follow_redirects=True,
    )

    resp = client.post(
        "/student/switch-branch",
        data={"branch_id": str(da_id), "target_exam_year": "2025"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Machine Learning" in resp.data

    with app.app_context():
        user = User.query.filter_by(email="priya@example.com").first()
        assert user.student_profile.selected_branch.code == "DA"
        assert user.student_profile.target_exam_year == 2025


def test_admin_portal_login_and_management(client, app):
    # Student login route rejects admin user
    resp = client.post(
        "/auth/login",
        data={"email": "admin@gateintelligence.local", "password": "Admin@Gate2026!"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/auth/admin/login" in resp.headers["Location"]

    # Admin login route succeeds
    admin_login = client.post(
        "/auth/admin/login",
        data={"email": "admin@gateintelligence.local", "password": "Admin@Gate2026!"},
        follow_redirects=True,
    )
    assert admin_login.status_code == 200
    assert b"Administrator Overview" in admin_login.data

    # Admin can view branches, syllabus, exam patterns, students, logs
    for path in (
        "/admin/branches",
        "/admin/syllabus",
        "/admin/exam-patterns",
        "/admin/students",
        "/admin/logs",
    ):
        page = client.get(path)
        assert page.status_code == 200
