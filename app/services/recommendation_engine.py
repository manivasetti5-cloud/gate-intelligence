"""AI Personalized Performance Advisor & 7-Day Revision Plan Generator."""

from datetime import date, timedelta
from typing import Any

from app.extensions import db
from app.models.analytics import (
    AIRecommendation,
    FormulaEntry,
    RevisionPlan,
    RevisionTask,
)
from app.models.syllabus import Branch, Subject
from app.services.analytics_service import get_student_analytics_bundle
from app.services.llm_client import (
    LLMSchemaError,
    LLMUnavailableError,
    generate_structured_json,
    is_llm_configured,
)


def generate_personalized_recommendation(
    student_id: int, branch_id: int, attempt_id: int | None = None
) -> AIRecommendation:
    """
    Generate a 10-point personalized GATE advisory report based strictly on real student history.
    Uses configured LLM when available, with a deterministic data-backed advisor fallback.
    """
    bundle = get_student_analytics_bundle(student_id, branch_id)
    perf = bundle["performance"]
    branch = Branch.query.get(branch_id)

    weak_topic_names = [tp.topic.name for tp in bundle["weak_topics"] if tp.topic][:5]
    strong_topic_names = [tp.topic.name for tp in bundle["strong_topics"] if tp.topic][:5]
    weak_subj_names = [s["name"] for s in bundle["weak_subjects"]][:3]
    strong_subj_names = [s["name"] for s in bundle["strong_subjects"]][:3]

    # Fetch relevant formulas for weak subjects
    weak_subj_ids = []
    if weak_subj_names:
        weak_subj_ids = [
            s.id for s in Subject.query.filter(Subject.name.in_(weak_subj_names)).all()
        ]
    formula_query = FormulaEntry.query.filter_by(branch_id=branch_id)
    if weak_subj_ids:
        formula_query = formula_query.filter(FormulaEntry.subject_id.in_(weak_subj_ids))
    suggested_formulas = [
        {"id": f.id, "title": f.title, "formula": f.formula_latex, "shortcut": f.shortcut_md or ""}
        for f in formula_query.limit(4).all()
    ]

    # Pick recommended next test configuration
    target_subj_id = weak_subj_ids[0] if weak_subj_ids else None
    rec_test_config = {
        "mode": "subject" if target_subj_id else "chapter",
        "subject_id": target_subj_id,
        "question_count": 20,
        "selection_mode": "weak_topic" if bundle["weak_topics"] else "unattempted",
    }

    if perf.total_attempts == 0:
        advice = {
            "1_performance_summary": "No completed tests yet. Take a baseline 10-question or subject-wise test to establish your real accuracy and speed profile.",
            "2_weak_topics": "Pending baseline diagnostic test.",
            "3_strong_topics": "Pending baseline diagnostic test.",
            "4_revision_recommendations": "Explore the official syllabus and take one diagnostic test per core subject.",
            "5_suggested_practice": "Start with a 10-question Subject-Wise test in your branch.",
            "6_time_management": "Aim for ~2 minutes per 1-mark question and ~3 minutes per 2-mark question.",
            "7_formula_recommendations": "Review the Formula & Shortcut Library before starting timed practice.",
            "8_shortcut_recommendations": "Use unit-dimensional checks and option elimination on MCQs.",
            "9_common_mistake_analysis": "No recorded mistakes yet; wrong answers will automatically appear in your Error Notebook.",
            "10_recommended_next_assessment": "Take a 10-question baseline diagnostic test now.",
        }
        model_used = "baseline_rule_advisor"
    else:
        advice = {
            "1_performance_summary": (
                f"Across {perf.total_attempts} completed assessment(s) in {branch.code if branch else ''}, "
                f"your average accuracy is {perf.avg_accuracy}% with an average pace of {perf.avg_speed_sec}s/question "
                f"and an attempt rate of {bundle['attempt_rate']}%. ({perf.readiness_confidence_label})"
            ),
            "2_weak_topics": ", ".join(weak_topic_names or weak_subj_names) or "No critical weak topics flagged yet.",
            "3_strong_topics": ", ".join(strong_topic_names or strong_subj_names) or "Build more attempts to confirm strengths.",
            "4_revision_recommendations": (
                f"Focus revision on {', '.join(weak_subj_names or weak_topic_names)}."
                if (weak_subj_names or weak_topic_names)
                else "Expand syllabus coverage to unattempted topics."
            ),
            "5_suggested_practice": (
                f"Attempt a targeted 20-question test prioritizing weak topics ({', '.join(weak_topic_names[:2]) or 'unresolved errors'})."
            ),
            "6_time_management": (
                f"You spent >180s on {bundle['excessive_time_count']} question(s). Practice skipping time-sink problems and returning via 'Mark for Review'."
                if bundle["excessive_time_count"] > 0
                else f"Your average speed ({perf.avg_speed_sec}s/Q) is balanced; keep monitoring 2-mark NAT pacing."
            ),
            "7_formula_recommendations": "; ".join(f["title"] for f in suggested_formulas) or "Review core branch formulas in Formula Library.",
            "8_shortcut_recommendations": "; ".join(f["shortcut"] for f in suggested_formulas if f["shortcut"]) or "Apply dimensional verification and boundary-value checks.",
            "9_common_mistake_analysis": (
                f"Detected {bundle['rapid_wrong_count']} rapid wrong answer(s) (<15s, possible guessing) and {bundle['repeated_errors']} repeated mistake(s). Review your Error Notebook before attempting new mocks."
            ),
            "10_recommended_next_assessment": (
                f"Targeted 20-question test on {weak_subj_names[0]}"
                if weak_subj_names
                else "10-question Unattempted Topic Practice"
            ),
        }
        model_used = "data_driven_advisor"

        if is_llm_configured():
            prompt = (
                "Generate concise, evidence-grounded GATE preparation advice from this real student telemetry.\n"
                "Do NOT invent stats or guarantee an official GATE rank.\n"
                f"Branch: {branch.code if branch else ''}\n"
                f"Total Attempts: {perf.total_attempts}, Avg Accuracy: {perf.avg_accuracy}%, "
                f"Avg Speed: {perf.avg_speed_sec}s/Q, Attempt Rate: {bundle['attempt_rate']}%, "
                f"Rapid Wrong (<15s): {bundle['rapid_wrong_count']}, Repeated Errors: {bundle['repeated_errors']}\n"
                f"Strong Subjects: {strong_subj_names}\nWeak Subjects: {weak_subj_names}\n"
                f"Weak Topics: {weak_topic_names}\n"
                'Return JSON with keys: "summary", "revision_recommendations", "time_management", "mistake_analysis", "next_assessment".'
            )
            try:
                parsed, llm_model = generate_structured_json(
                    prompt, required_keys=["summary", "revision_recommendations"]
                )
                advice["1_performance_summary"] = str(parsed.get("summary", advice["1_performance_summary"]))
                advice["4_revision_recommendations"] = str(parsed.get("revision_recommendations", advice["4_revision_recommendations"]))
                advice["6_time_management"] = str(parsed.get("time_management", advice["6_time_management"]))
                advice["9_common_mistake_analysis"] = str(parsed.get("mistake_analysis", advice["9_common_mistake_analysis"]))
                advice["10_recommended_next_assessment"] = str(parsed.get("next_assessment", advice["10_recommended_next_assessment"]))
                model_used = f"llm:{llm_model}"
            except (LLMUnavailableError, LLMSchemaError):
                pass

    rec = AIRecommendation(
        student_id=student_id,
        attempt_id=attempt_id,
        summary_md=advice["1_performance_summary"],
        weak_topics_json=weak_topic_names or weak_subj_names,
        strong_topics_json=strong_topic_names or strong_subj_names,
        suggested_formulas_json=suggested_formulas,
        recommended_test_config_json=rec_test_config,
        advice_json=advice,
        model_used=model_used,
    )
    db.session.add(rec)
    db.session.commit()
    return rec


def create_seven_day_revision_plan(student_id: int, branch_id: int, subject_id: int | None = None) -> RevisionPlan:
    """Create a personalized, editable 7-day preparation schedule targeting weak topics."""
    bundle = get_student_analytics_bundle(student_id, branch_id)
    focus_subject = Subject.query.get(subject_id) if subject_id else None
    if not focus_subject and bundle["weak_subjects"]:
        focus_subject = Subject.query.filter_by(name=bundle["weak_subjects"][0]["name"]).first()

    focus_label = focus_subject.name if focus_subject else "Core Branch Topics"
    topics = []
    if focus_subject:
        for ch in focus_subject.chapters:
            for t in ch.topics:
                topics.append(t)

    start = date.today()
    plan = RevisionPlan(
        student_id=student_id,
        branch_id=branch_id,
        title=f"7-Day Focus Plan: {focus_label}",
        focus_subject_id=focus_subject.id if focus_subject else None,
        start_date=start,
        end_date=start + timedelta(days=6),
        status="active",
    )
    db.session.add(plan)
    db.session.flush()

    t1 = topics[0] if len(topics) > 0 else None
    t2 = topics[1] if len(topics) > 1 else t1
    t3 = topics[2] if len(topics) > 2 else t1

    schedule_rows = [
        (1, f"Revise {t1.name if t1 else focus_label} & core formulas", "Review concepts and formula sheet without timing pressure.", t1, "revise"),
        (2, f"Study {t2.name if t2 else focus_label} & worked examples", "Focus on standard GATE problem archetypes and edge cases.", t2, "revise"),
        (3, f"Revise {t3.name if t3 else focus_label} & solving shortcuts", "Practice shortcut derivations and unit verification.", t3, "revise"),
        (4, f"Attempt 20 practice questions on {focus_label}", "Take a timed 20-question subject-wise assessment.", t1, "practice"),
        (5, "Review Error Notebook & bookmark tricky problems", "Re-solve every missed question and add personal revision notes.", None, "review_errors"),
        (6, "Take a mixed-topic 30-question timed assessment", "Combine strong and weak subjects to build context-switching speed.", None, "practice"),
        (7, "Reassess performance & update GATE readiness", "Compare accuracy and speed trends against Day 1 baseline.", None, "mock"),
    ]

    for day_num, title, desc, tp, t_type in schedule_rows:
        db.session.add(
            RevisionTask(
                plan_id=plan.id,
                day_number=day_num,
                title=title,
                description=desc,
                target_topic_id=tp.id if tp else None,
                task_type=t_type,
                is_completed=False,
            )
        )

    db.session.commit()
    return plan
