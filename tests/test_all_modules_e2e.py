"""End-to-end audit test verifying every Student and Admin module works without placeholders or 500s."""

from app.models.question import Question
from app.models.syllabus import Branch, Subject
from app.services.question_service import create_question_record
from app.services.syllabus_service import resolve_syllabus_version


def test_every_student_module_and_edge_cases(client, app):
    with app.app_context():
        cs = Branch.query.filter_by(code="CS").first()
        sv = resolve_syllabus_version(cs.id, 2026)
        subj = Subject.query.filter_by(syllabus_version_id=sv.id, code="CS-OS").first()
        ch = subj.chapters[0]
        tp = ch.topics[0]
        cp = tp.concepts[0]
        cs_id, subj_id, ch_id, tp_id, cp_id = cs.id, subj.id, ch.id, tp.id, cp.id

    # Register & verify dashboard
    client.post(
        "/auth/register",
        data={
            "full_name": "Audit Student",
            "email": "audit_student@example.com",
            "branch_id": str(cs_id),
            "target_exam_year": "2026",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
        follow_redirects=True,
    )

    # Profile update & change password
    assert client.post(
        "/student/profile",
        data={
            "full_name": "Audit Student Updated",
            "branch_id": str(cs_id),
            "target_exam_year": "2026",
            "daily_study_minutes": "180",
        },
        follow_redirects=True,
    ).status_code == 200

    assert client.post(
        "/student/change-password",
        data={
            "current_password": "Password123!",
            "new_password": "NewPassword456!",
            "confirm_password": "NewPassword456!",
        },
        follow_redirects=True,
    ).status_code == 200

    # Verify new password works
    client.post("/auth/logout", follow_redirects=True)
    login_resp = client.post(
        "/auth/login",
        data={"email": "audit_student@example.com", "password": "NewPassword456!"},
        follow_redirects=True,
    )
    assert b"Audit Student Updated" in login_resp.data

    # Test configuration prefill from PYQ Practice / AI Practice / Syllabus Explorer
    pyq_cfg = client.get("/assessments/configure?mode=subject&question_source=PYQ")
    assert pyq_cfg.status_code == 200
    assert b'value="PYQ" selected' in pyq_cfg.data

    concept_cfg = client.get(
        f"/assessments/configure?mode=concept&subject_id={subj_id}&chapter_id={ch_id}&topic_id={tp_id}&concept_id={cp_id}"
    )
    assert concept_cfg.status_code == 200

    # Cascade API endpoints
    assert client.get(f"/assessments/api/cascade?subject_id={subj_id}").status_code == 200
    assert client.get(f"/assessments/api/cascade?chapter_id={ch_id}").status_code == 200
    assert client.get(f"/assessments/api/cascade?topic_id={tp_id}").status_code == 200

    # All student GET modules return 200 and no placeholder text
    student_routes = [
        "/student/dashboard",
        "/student/syllabus",
        "/student/profile",
        "/assessments/configure",
        "/assessments/history",
        "/questions/bank",
        "/questions/bookmarks",
        "/questions/error-notebook",
        "/analytics/performance",
        "/analytics/readiness",
        "/analytics/advisor",
        "/analytics/revision",
        "/analytics/formulas",
    ]
    for route in student_routes:
        r = client.get(route)
        assert r.status_code == 200, f"Route failed: {route}"
        assert b"activates in Phase" not in r.data
        assert b"Upcoming Phase" not in r.data


def test_every_admin_module_settings_syllabus_and_verification_guards(client, app):
    client.post(
        "/auth/admin/login",
        data={"email": "admin@gateintelligence.local", "password": "Admin@Gate2026!"},
        follow_redirects=True,
    )

    # All admin GET routes return 200 with zero placeholder pages
    admin_routes = [
        "/admin/overview",
        "/admin/branches",
        "/admin/syllabus",
        "/admin/exam-patterns",
        "/admin/students",
        "/admin/logs",
        "/admin/question-bank",
        "/admin/upload-paper",
        "/admin/jobs",
        "/admin/verification",
        "/admin/ai-generation",
        "/admin/analytics",
        "/admin/settings",
    ]
    for route in admin_routes:
        r = client.get(route)
        assert r.status_code == 200, f"Admin route failed: {route}"
        assert b"activates in" not in r.data
        assert b"Upcoming Phase" not in r.data

    # Verification guard: reject invalid NAT input and empty answer without 500
    with app.app_context():
        cs = Branch.query.filter_by(code="CS").first()
        sv = resolve_syllabus_version(cs.id, 2026)
        subj = Subject.query.filter_by(syllabus_version_id=sv.id).first()
        pending_nat = create_question_record(
            branch_id=cs.id,
            subject_id=subj.id,
            chapter_id=None,
            topic_id=None,
            concept_id=None,
            source_type="PYQ",
            question_type="NAT",
            marks=2,
            difficulty="medium",
            statement_md="Pending NAT question without answer yet.",
            correct_answer_json={},
            explanation_json={},
            verification_status="needs_manual_review",
            is_published=False,
        )
        from app.extensions import db

        db.session.commit()
        q_id = pending_nat.id

    # Attempt publish with empty answer -> must stay unpublished with warning
    r1 = client.post(
        "/admin/verification",
        data={"question_id": str(q_id), "action": "approve_publish", "override_answer": ""},
        follow_redirects=True,
    )
    assert r1.status_code == 200
    assert b"has no answer key yet" in r1.data

    # Attempt publish with non-numeric NAT -> must not 500
    r2 = client.post(
        "/admin/verification",
        data={"question_id": str(q_id), "action": "approve_publish", "override_answer": "not-a-number"},
        follow_redirects=True,
    )
    assert r2.status_code == 200
    assert b"valid numeric value" in r2.data

    # Valid NAT publish succeeds
    r3 = client.post(
        "/admin/verification",
        data={"question_id": str(q_id), "action": "approve_publish", "override_answer": "12.5"},
        follow_redirects=True,
    )
    assert r3.status_code == 200
    with app.app_context():
        q = Question.query.get(q_id)
        assert q.verification_status == "verified"
        assert q.is_published is True
        assert q.correct_answer_json["value"] == 12.5

    # Settings: disable student registration and verify /auth/register blocks signup
    s_resp = client.post(
        "/admin/settings",
        data={
            "auto_publish_verified_pdf": "on",
            "ocr_enabled": "on",
            "default_question_count": "15",
            "default_duration_minutes": "30",
        },
        follow_redirects=True,
    )
    assert s_resp.status_code == 200
    assert b"Platform settings saved" in s_resp.data

    client.post("/auth/logout", follow_redirects=True)
    reg_blocked = client.get("/auth/register", follow_redirects=True)
    assert b"registrations are currently paused" in reg_blocked.data
