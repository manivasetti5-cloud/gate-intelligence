"""Longitudinal student performance analytics, guessing/speed diagnostics, GATE readiness, and admin metrics."""

from typing import Any

from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.analytics import StudentPerformance, TopicPerformance
from app.models.attempt import ErrorNotebookEntry, Result, StudentAttempt, StudentResponse
from app.models.question import Question, QuestionSource
from app.models.syllabus import Branch, Subject, Topic
from app.models.test import Test
from app.models.user import User
from app.services.syllabus_service import count_syllabus_nodes, resolve_syllabus_version


def refresh_student_analytics(student_id: int, branch_id: int) -> StudentPerformance:
    """Recompute longitudinal StudentPerformance & TopicPerformance strictly from real PostgreSQL attempts."""
    attempts = (
        StudentAttempt.query.options(
            joinedload(StudentAttempt.result),
            joinedload(StudentAttempt.test).joinedload(Test.configuration),
            joinedload(StudentAttempt.responses).joinedload(StudentResponse.question),
        )
        .filter(
            StudentAttempt.student_id == student_id,
            StudentAttempt.status.in_(["submitted", "auto_submitted"]),
        )
        .order_by(StudentAttempt.submitted_at.asc())
        .all()
    )

    branch_attempts = [a for a in attempts if a.test and a.test.branch_id == branch_id]
    results = [a.result for a in branch_attempts if a.result]
    total_attempts = len(branch_attempts)

    avg_acc = round(sum(r.accuracy_percent for r in results) / len(results), 2) if results else 0.0
    score_pcts = [
        round((r.total_marks_obtained / r.max_marks) * 100.0, 2) if r.max_marks > 0 else 0.0
        for r in results
    ]
    best_pct = max(score_pcts, default=0.0)
    avg_speed = (
        round(sum(r.avg_time_per_question for r in results) / len(results), 2) if results else 0.0
    )

    # Aggregate per-topic statistics across all completed attempts in this branch
    topic_stats: dict[int, dict[str, Any]] = {}
    attempted_topic_ids: set[int] = set()

    for att in branch_attempts:
        for resp in att.responses:
            q = resp.question
            if not q or not q.topic_id:
                continue
            attempted_topic_ids.add(q.topic_id)
            st = topic_stats.setdefault(
                q.topic_id,
                {
                    "subject_id": q.subject_id,
                    "chapter_id": q.chapter_id,
                    "attempts": 0,
                    "correct": 0,
                    "incorrect": 0,
                    "time_sum": 0,
                },
            )
            if resp.is_correct is True:
                st["attempts"] += 1
                st["correct"] += 1
            elif resp.is_correct is False:
                st["attempts"] += 1
                st["incorrect"] += 1
            st["time_sum"] += resp.time_spent_seconds or 0

    for topic_id, st in topic_stats.items():
        att_cnt = st["attempts"]
        acc = round((st["correct"] / att_cnt) * 100.0, 2) if att_cnt > 0 else 0.0
        avg_t = round(st["time_sum"] / max(1, att_cnt), 2)
        if att_cnt >= 2 and acc >= 75.0:
            strength = "strong"
        elif att_cnt >= 1 and acc < 50.0:
            strength = "weak"
        else:
            strength = "moderate"

        tp = TopicPerformance.query.filter_by(student_id=student_id, topic_id=topic_id).first()
        if not tp:
            tp = TopicPerformance(
                student_id=student_id,
                subject_id=st["subject_id"],
                chapter_id=st["chapter_id"],
                topic_id=topic_id,
            )
            db.session.add(tp)
        tp.attempts_count = att_cnt
        tp.correct_count = st["correct"]
        tp.incorrect_count = st["incorrect"]
        tp.accuracy_percent = acc
        tp.avg_time_sec = avg_t
        tp.strength_status = strength

    # Compute GATE Readiness Score (explicitly an internal performance estimate)
    sv = resolve_syllabus_version(branch_id, 2026)
    total_topics = count_syllabus_nodes(sv.id)["topics"] if sv else 1
    coverage_pct = min(100.0, (len(attempted_topic_ids) / max(1, total_topics)) * 100.0)

    mock_scores = [
        round((a.result.total_marks_obtained / a.result.max_marks) * 100.0, 2)
        for a in branch_attempts
        if a.result and a.result.max_marks > 0 and a.test.configuration.mode == "full_mock"
    ]
    mock_component = sum(mock_scores) / len(mock_scores) if mock_scores else (sum(score_pcts) / len(score_pcts) if score_pcts else 0.0)
    consistency_component = min(100.0, total_attempts * 15.0)

    if total_attempts == 0:
        readiness = 0.0
        conf_label = "No Assessment Data Yet"
    elif total_attempts < 3:
        readiness = round(0.40 * avg_acc + 0.25 * coverage_pct + 0.20 * max(0.0, mock_component) + 0.15 * consistency_component, 1)
        conf_label = "Early Baseline (<3 tests — take more tests for reliable readiness)"
    elif total_attempts < 7:
        readiness = round(0.40 * avg_acc + 0.25 * coverage_pct + 0.20 * max(0.0, mock_component) + 0.15 * consistency_component, 1)
        conf_label = "Moderate Evidence"
    else:
        readiness = round(0.40 * avg_acc + 0.25 * coverage_pct + 0.20 * max(0.0, mock_component) + 0.15 * consistency_component, 1)
        conf_label = "Strong Longitudinal Data"

    sp = StudentPerformance.query.filter_by(student_id=student_id, branch_id=branch_id).first()
    if not sp:
        sp = StudentPerformance(student_id=student_id, branch_id=branch_id)
        db.session.add(sp)
    sp.total_attempts = total_attempts
    sp.avg_accuracy = avg_acc
    sp.best_score_percent = best_pct
    sp.avg_speed_sec = avg_speed
    sp.readiness_score = max(0.0, min(100.0, readiness))
    sp.readiness_confidence_label = conf_label
    db.session.commit()
    return sp


def get_student_analytics_bundle(student_id: int, branch_id: int) -> dict[str, Any]:
    """Build complete analytics payload for Chart.js dashboards and AI advisor."""
    perf = refresh_student_analytics(student_id, branch_id)

    attempts = (
        StudentAttempt.query.options(joinedload(StudentAttempt.result), joinedload(StudentAttempt.test))
        .filter(
            StudentAttempt.student_id == student_id,
            StudentAttempt.status.in_(["submitted", "auto_submitted"]),
        )
        .order_by(StudentAttempt.submitted_at.asc())
        .all()
    )
    branch_attempts = [a for a in attempts if a.test and a.test.branch_id == branch_id and a.result]

    trend_labels = [a.submitted_at.strftime("%b %d") if a.submitted_at else f"#{a.id}" for a in branch_attempts]
    trend_scores = [
        round((a.result.total_marks_obtained / a.result.max_marks) * 100.0, 1) if a.result.max_marks > 0 else 0.0
        for a in branch_attempts
    ]
    trend_accuracy = [a.result.accuracy_percent for a in branch_attempts]

    # Subject-wise and difficulty-wise aggregation
    subject_agg: dict[str, dict[str, Any]] = {}
    diff_agg: dict[str, dict[str, Any]] = {}
    rapid_wrong_count = 0
    excessive_time_count = 0
    total_answered = 0
    total_presented = 0

    for att in branch_attempts:
        for resp in att.responses:
            q = resp.question
            if not q:
                continue
            total_presented += 1
            if resp.is_correct is not None:
                total_answered += 1
                if resp.is_correct is False and (resp.time_spent_seconds or 0) < 15:
                    rapid_wrong_count += 1
            if (resp.time_spent_seconds or 0) > 180:
                excessive_time_count += 1

            s_name = q.subject.name if q.subject else "General"
            sb = subject_agg.setdefault(s_name, {"name": s_name, "correct": 0, "incorrect": 0, "unanswered": 0})
            dbkt = diff_agg.setdefault(q.difficulty.title(), {"name": q.difficulty.title(), "correct": 0, "incorrect": 0})
            if resp.is_correct is True:
                sb["correct"] += 1
                dbkt["correct"] += 1
            elif resp.is_correct is False:
                sb["incorrect"] += 1
                dbkt["incorrect"] += 1
            else:
                sb["unanswered"] += 1

    subject_rows = []
    for row in subject_agg.values():
        att_n = row["correct"] + row["incorrect"]
        acc = round((row["correct"] / att_n) * 100.0, 1) if att_n > 0 else 0.0
        subject_rows.append({**row, "accuracy": acc, "attempted": att_n})
    subject_rows.sort(key=lambda x: x["accuracy"], reverse=True)

    strong_subjects = [r for r in subject_rows if r["attempted"] >= 1 and r["accuracy"] >= 70.0]
    weak_subjects = [r for r in subject_rows if r["attempted"] >= 1 and r["accuracy"] < 60.0]

    topic_rows = (
        TopicPerformance.query.options(joinedload(TopicPerformance.topic), joinedload(TopicPerformance.subject))
        .filter_by(student_id=student_id)
        .order_by(TopicPerformance.accuracy_percent.asc())
        .all()
    )
    weak_topics = [tp for tp in topic_rows if tp.strength_status == "weak"]
    strong_topics = [tp for tp in topic_rows if tp.strength_status == "strong"]

    attempt_rate = round((total_answered / total_presented) * 100.0, 1) if total_presented > 0 else 0.0
    repeated_errors = ErrorNotebookEntry.query.filter(
        ErrorNotebookEntry.student_id == student_id, ErrorNotebookEntry.mistake_count >= 2
    ).count()

    sv = resolve_syllabus_version(branch_id, 2026)
    total_topics_in_branch = count_syllabus_nodes(sv.id)["topics"] if sv else 0
    covered_topics_count = len({tp.topic_id for tp in topic_rows if tp.attempts_count > 0})
    unattempted_topics = []
    if sv:
        attempted_ids = {tp.topic_id for tp in topic_rows}
        all_topics = (
            Topic.query.join(Topic.chapter).join(Subject, Topic.chapter.has(Subject.syllabus_version_id == sv.id)).all()
            if False
            else []
        )
        subjects = Subject.query.filter_by(syllabus_version_id=sv.id).all()
        for s in subjects:
            for ch in s.chapters:
                for t in ch.topics:
                    if t.id not in attempted_ids:
                        unattempted_topics.append({"subject": s.name, "topic": t.name})

    return {
        "performance": perf,
        "trend_labels": trend_labels,
        "trend_scores": trend_scores,
        "trend_accuracy": trend_accuracy,
        "subject_rows": subject_rows,
        "difficulty_rows": list(diff_agg.values()),
        "strong_subjects": strong_subjects,
        "weak_subjects": weak_subjects,
        "weak_topics": weak_topics,
        "strong_topics": strong_topics,
        "attempt_rate": attempt_rate,
        "rapid_wrong_count": rapid_wrong_count,
        "excessive_time_count": excessive_time_count,
        "repeated_errors": repeated_errors,
        "covered_topics_count": covered_topics_count,
        "total_topics_in_branch": total_topics_in_branch,
        "unattempted_topics": unattempted_topics[:10],
    }


def get_platform_analytics() -> dict[str, Any]:
    """Aggregate platform-wide metrics for the Admin Analytics dashboard."""
    branches = Branch.query.order_by(Branch.code.asc()).all()
    by_branch = [
        {"code": b.code, "questions": Question.query.filter_by(branch_id=b.id).count()}
        for b in branches
    ]
    by_source = []
    for src in ("PYQ", "AI_GENERATED"):
        cnt = Question.query.join(Question.source).filter(QuestionSource.source_type == src).count()
        by_source.append({"source": src, "count": cnt})

    total_students = User.query.join(User.role).filter_by(name="student").count()
    total_attempts = StudentAttempt.query.filter(
        StudentAttempt.status.in_(["submitted", "auto_submitted"])
    ).count()
    all_results = Result.query.all()
    avg_platform_accuracy = (
        round(sum(r.accuracy_percent for r in all_results) / len(all_results), 1)
        if all_results
        else 0.0
    )

    return {
        "by_branch": by_branch,
        "by_source": by_source,
        "total_students": total_students,
        "total_attempts": total_attempts,
        "total_questions": Question.query.count(),
        "verified_questions": Question.query.filter_by(verification_status="verified").count(),
        "avg_platform_accuracy": avg_platform_accuracy,
    }
