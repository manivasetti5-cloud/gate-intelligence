"""Phase 2 tests: GATE scoring, anti-leak session security, expiry auto-submit, error notebook, and reattempt."""

from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.attempt import ErrorNotebookEntry, StudentAttempt
from app.models.question import Question
from app.models.syllabus import Branch
from app.services.evaluation_service import evaluate_attempt


def _register_cs_student(client, app, email="student1@example.com"):
    with app.app_context():
        cs_id = Branch.query.filter_by(code="CS").first().id
    resp = client.post(
        "/auth/register",
        data={
            "full_name": "Test Student",
            "email": email,
            "branch_id": str(cs_id),
            "target_exam_year": "2026",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200


def test_full_exam_lifecycle_gate_scoring_and_anti_leak(client, app):
    _register_cs_student(client, app, "cs_exam@example.com")

    # Start a full mock test in CS (picks up seeded CS + GA sample verified questions)
    start_resp = client.post(
        "/assessments/start",
        data={"mode": "full_mock", "question_source": "MIXED"},
        follow_redirects=False,
    )
    assert start_resp.status_code == 302
    exam_url = start_resp.headers["Location"]
    assert "/assessments/exam/" in exam_url
    attempt_id = int(exam_url.rsplit("/", 1)[-1])

    # Active session state must NEVER expose answer keys or explanations
    state_resp = client.get(f"/assessments/exam/{attempt_id}/state")
    assert state_resp.status_code == 200
    state_json = state_resp.get_json()
    assert state_json["status"] == "in_progress"
    assert len(state_json["questions"]) >= 5
    for q in state_json["questions"]:
        assert "correct_answer_json" not in q
        assert "explanation_json" not in q
        for opt in q.get("options", []):
            assert "is_correct" not in opt

    # Result endpoint must redirect back to exam while attempt is in_progress
    early_result = client.get(f"/results/{attempt_id}", follow_redirects=False)
    assert early_result.status_code == 302
    assert f"/assessments/exam/{attempt_id}" in early_result.headers["Location"]

    # Look up true answers in DB for verification of exact GATE scoring rules
    with app.app_context():
        attempt = StudentAttempt.query.get(attempt_id)
        answers_by_tq = {}
        for tq in attempt.test.test_questions:
            q = Question.query.get(tq.question_id)
            answers_by_tq[tq.id] = {
                "type": q.question_type,
                "marks": q.marks,
                "correct": q.correct_answer_json,
            }

    # Answer: 1st MCQ correctly, 2nd MCQ (if any) wrongly, MSQ partially wrong (should get 0, NOT negative), NAT correctly
    mcq_seen = 0
    expected_marks = 0.0
    expected_wrong_count = 0

    for idx, q_item in enumerate(state_json["questions"]):
        tq_id = q_item["test_question_id"]
        meta = answers_by_tq[tq_id]
        if meta["type"] == "MCQ":
            mcq_seen += 1
            if mcq_seen == 1:
                chosen = [meta["correct"]["option"]]
                expected_marks += meta["marks"]
            else:
                wrong_opt = "A" if meta["correct"]["option"] != "A" else "B"
                chosen = [wrong_opt]
                expected_marks -= round(meta["marks"] / 3.0, 4)
                expected_wrong_count += 1
            save_r = client.post(
                f"/assessments/exam/{attempt_id}/save",
                json={
                    "test_question_id": tq_id,
                    "selected_options": chosen,
                    "palette_status": "answered",
                    "current_question_index": idx,
                    "time_delta_seconds": 12,
                },
            )
            assert save_r.status_code == 200
        elif meta["type"] == "MSQ":
            # Choose only 1 option when multiple are correct -> wrong in GATE, 0 marks (no negative)
            partial = [meta["correct"]["options"][0]]
            expected_wrong_count += 1
            save_r = client.post(
                f"/assessments/exam/{attempt_id}/save",
                json={
                    "test_question_id": tq_id,
                    "selected_options": partial,
                    "palette_status": "answered_and_marked",
                    "current_question_index": idx,
                    "time_delta_seconds": 20,
                },
            )
            assert save_r.status_code == 200
        elif meta["type"] == "NAT":
            val = meta["correct"]["value"]
            expected_marks += meta["marks"]
            save_r = client.post(
                f"/assessments/exam/{attempt_id}/save",
                json={
                    "test_question_id": tq_id,
                    "nat_answer_value": str(val),
                    "palette_status": "answered",
                    "current_question_index": idx,
                    "time_delta_seconds": 25,
                },
            )
            assert save_r.status_code == 200

    # Submit test
    sub_resp = client.post(
        f"/assessments/exam/{attempt_id}/submit",
        json={"auto_submit": False},
    )
    assert sub_resp.status_code == 200
    assert sub_resp.get_json()["submitted"] is True

    with app.app_context():
        attempt = StudentAttempt.query.get(attempt_id)
        assert attempt.status == "submitted"
        assert attempt.result is not None
        assert abs(attempt.result.total_marks_obtained - round(expected_marks, 2)) < 0.05
        assert attempt.result.incorrect_count == expected_wrong_count
        # Wrong questions should automatically be in Error Notebook
        assert ErrorNotebookEntry.query.filter_by(student_id=attempt.student_id).count() == expected_wrong_count

    # Result page renders score and explanations
    res_page = client.get(f"/results/{attempt_id}")
    assert res_page.status_code == 200
    assert b"Question-Wise Answer Key" in res_page.data

    # Reattempt unresolved errors creates a new test
    re_resp = client.post(
        "/assessments/reattempt",
        data={"selection_mode": "incorrect"},
        follow_redirects=False,
    )
    assert re_resp.status_code == 302
    assert "/assessments/exam/" in re_resp.headers["Location"]


def test_expired_attempt_auto_submits_and_cross_student_isolation(client, app):
    _register_cs_student(client, app, "s1@example.com")

    start_resp = client.post(
        "/assessments/start",
        data={"mode": "full_mock", "question_source": "MIXED"},
        follow_redirects=False,
    )
    attempt_id = int(start_resp.headers["Location"].rsplit("/", 1)[-1])

    # Expire attempt on server side
    with app.app_context():
        att = StudentAttempt.query.get(attempt_id)
        att.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        db.session.commit()

    # Fetching state should auto-submit instead of returning active exam
    state_resp = client.get(f"/assessments/exam/{attempt_id}/state")
    assert state_resp.status_code == 200
    assert state_resp.get_json()["redirect_to_result"] is True

    with app.app_context():
        att = StudentAttempt.query.get(attempt_id)
        assert att.status == "auto_submitted"
        # Idempotent re-evaluation returns same result
        r1 = att.result
        r2 = evaluate_attempt(att.id)
        assert r1.id == r2.id

    # Second student cannot view first student's result
    client.post("/auth/logout", follow_redirects=True)
    _register_cs_student(client, app, "s2@example.com")
    forbidden_res = client.get(f"/results/{attempt_id}")
    assert forbidden_res.status_code == 404


def test_daily_challenge_and_bookmarks(client, app):
    _register_cs_student(client, app, "daily@example.com")
    dc_resp = client.get("/assessments/daily-challenge", follow_redirects=False)
    assert dc_resp.status_code == 302
    assert "/assessments/exam/" in dc_resp.headers["Location"]

    with app.app_context():
        q = Question.query.first()
        q_id = q.id

    bm = client.post(f"/questions/{q_id}/bookmark", json={})
    assert bm.status_code == 200
    assert bm.get_json()["bookmarked"] is True
    assert client.get("/questions/bookmarks").status_code == 200
    assert client.get("/questions/bank").status_code == 200
    assert client.get("/assessments/history").status_code == 200
