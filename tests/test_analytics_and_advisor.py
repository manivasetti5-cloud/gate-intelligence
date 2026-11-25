"""Phase 4 tests: longitudinal analytics, GATE readiness, AI advisor, 7-day revision plan, and formulas."""

from app.models.analytics import AIRecommendation, FormulaEntry, RevisionPlan, StudentPerformance
from app.models.attempt import StudentAttempt
from app.models.question import Question
from app.models.syllabus import Branch


def test_longitudinal_analytics_advisor_readiness_and_revision(client, app):
    with app.app_context():
        cs_id = Branch.query.filter_by(code="CS").first().id

    # Register student
    client.post(
        "/auth/register",
        data={
            "full_name": "Analytics Tester",
            "email": "analytics@example.com",
            "branch_id": str(cs_id),
            "target_exam_year": "2026",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
        follow_redirects=True,
    )

    # Complete a mock test
    start_resp = client.post(
        "/assessments/start",
        data={"mode": "full_mock", "question_source": "MIXED"},
        follow_redirects=False,
    )
    attempt_id = int(start_resp.headers["Location"].rsplit("/", 1)[-1])
    state_json = client.get(f"/assessments/exam/{attempt_id}/state").get_json()

    with app.app_context():
        attempt = StudentAttempt.query.get(attempt_id)
        answers = {
            tq.id: Question.query.get(tq.question_id) for tq in attempt.test.test_questions
        }

    for idx, q_item in enumerate(state_json["questions"]):
        tq_id = q_item["test_question_id"]
        q_obj = answers[tq_id]
        if q_obj.question_type == "MCQ":
            # Answer first MCQ correctly, others wrong rapidly (<15s)
            opt = q_obj.correct_answer_json["option"] if idx == 0 else ("C" if q_obj.correct_answer_json["option"] != "C" else "D")
            client.post(
                f"/assessments/exam/{attempt_id}/save",
                json={
                    "test_question_id": tq_id,
                    "selected_options": [opt],
                    "palette_status": "answered",
                    "current_question_index": idx,
                    "time_delta_seconds": 10,
                },
            )
        elif q_obj.question_type == "NAT":
            client.post(
                f"/assessments/exam/{attempt_id}/save",
                json={
                    "test_question_id": tq_id,
                    "nat_answer_value": str(q_obj.correct_answer_json["value"]),
                    "palette_status": "answered",
                    "current_question_index": idx,
                    "time_delta_seconds": 30,
                },
            )

    client.post(f"/assessments/exam/{attempt_id}/submit", json={"auto_submit": False})

    # Performance & Readiness pages
    perf_page = client.get("/analytics/performance")
    assert perf_page.status_code == 200
    assert b"Score &amp; Accuracy Trend" in perf_page.data

    ready_page = client.get("/analytics/readiness")
    assert ready_page.status_code == 200
    assert b"internal diagnostic estimate" in ready_page.data

    with app.app_context():
        sp = StudentPerformance.query.first()
        assert sp is not None
        assert sp.total_attempts == 1
        assert "Early Baseline" in sp.readiness_confidence_label

    # AI Advisor generates structured 10-point report
    adv_resp = client.post("/analytics/advisor", follow_redirects=True)
    assert adv_resp.status_code == 200
    assert b"Recommended Next Assessment" in adv_resp.data
    with app.app_context():
        rec = AIRecommendation.query.first()
        assert rec is not None
        assert "1_performance_summary" in rec.advice_json

    # 7-Day Revision Plan generation, toggle, and edit
    plan_resp = client.post("/analytics/revision/generate", data={}, follow_redirects=True)
    assert plan_resp.status_code == 200
    assert b"Day 1" in plan_resp.data
    assert b"Day 7" in plan_resp.data

    with app.app_context():
        plan = RevisionPlan.query.first()
        assert plan is not None
        assert len(plan.tasks) == 7
        first_task_id = plan.tasks[0].id

    client.post(f"/analytics/revision/task/{first_task_id}/toggle", follow_redirects=True)
    client.post(
        f"/analytics/revision/task/{first_task_id}/edit",
        data={"title": "Custom Revised Day 1 Goal", "description": "Updated notes"},
        follow_redirects=True,
    )
    with app.app_context():
        plan = RevisionPlan.query.first()
        t1 = next(t for t in plan.tasks if t.id == first_task_id)
        assert t1.is_completed is True
        assert t1.title == "Custom Revised Day 1 Goal"

    # Formula Library
    with app.app_context():
        assert FormulaEntry.query.count() >= 10
    formula_page = client.get("/analytics/formulas?q=Deadlock")
    assert formula_page.status_code == 200
    assert b"Minimum Resources for Deadlock Freedom" in formula_page.data


def test_admin_platform_analytics(client):
    client.post(
        "/auth/admin/login",
        data={"email": "admin@gateintelligence.local", "password": "Admin@Gate2026!"},
        follow_redirects=True,
    )
    resp = client.get("/admin/analytics")
    assert resp.status_code == 200
    assert b"Questions by GATE Branch" in resp.data
