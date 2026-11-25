"""Assessment configuration and balanced GATE question selection engine."""

from datetime import date
import random

from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.attempt import Bookmark, ErrorNotebookEntry, StudentResponse, StudentAttempt
from app.models.question import Question, QuestionSource
from app.models.syllabus import Branch, Chapter, Concept, Subject, Topic
from app.models.test import Test, TestConfiguration, TestQuestion
from app.services.syllabus_service import get_exam_pattern, resolve_syllabus_version


def _eligible_question_query(
    *,
    branch_id: int,
    question_source: str = "MIXED",
    difficulty: str = "mixed",
    question_type: str = "ALL",
    subject_id: int | None = None,
    chapter_id: int | None = None,
    topic_id: int | None = None,
    concept_id: int | None = None,
):
    """Build base SQLAlchemy query for verified, published questions matching filters."""
    query = (
        Question.query.join(Question.source)
        .options(joinedload(Question.subject))
        .filter(
            Question.branch_id == branch_id,
            Question.is_published.is_(True),
            Question.verification_status == "verified",
        )
    )

    if question_source and question_source != "MIXED":
        query = query.filter(QuestionSource.source_type == question_source)
    if difficulty and difficulty != "mixed":
        query = query.filter(Question.difficulty == difficulty)
    if question_type and question_type != "ALL":
        query = query.filter(Question.question_type == question_type)
    if subject_id:
        query = query.filter(Question.subject_id == subject_id)
    if chapter_id:
        query = query.filter(Question.chapter_id == chapter_id)
    if topic_id:
        query = query.filter(Question.topic_id == topic_id)
    if concept_id:
        query = query.filter(Question.concept_id == concept_id)

    return query


def _apply_selection_mode(
    candidates: list[Question],
    *,
    student_id: int,
    selection_mode: str,
) -> list[Question]:
    """Filter or prioritize candidate questions based on student history."""
    if not candidates or selection_mode == "random":
        pool = list(candidates)
        random.shuffle(pool)
        return pool

    candidate_ids = [q.id for q in candidates]

    if selection_mode == "bookmarked":
        bookmarked_ids = {
            b.question_id
            for b in Bookmark.query.filter(
                Bookmark.student_id == student_id, Bookmark.question_id.in_(candidate_ids)
            ).all()
        }
        filtered = [q for q in candidates if q.id in bookmarked_ids]
        random.shuffle(filtered)
        return filtered

    if selection_mode == "incorrect":
        err_ids = {
            e.question_id
            for e in ErrorNotebookEntry.query.filter(
                ErrorNotebookEntry.student_id == student_id,
                ErrorNotebookEntry.status == "unresolved",
                ErrorNotebookEntry.question_id.in_(candidate_ids),
            ).all()
        }
        filtered = [q for q in candidates if q.id in err_ids]
        random.shuffle(filtered)
        return filtered

    if selection_mode == "unattempted":
        attempted_ids = {
            r.question_id
            for r in db.session.query(StudentResponse.question_id)
            .join(StudentAttempt, StudentResponse.attempt_id == StudentAttempt.id)
            .filter(
                StudentAttempt.student_id == student_id,
                StudentResponse.question_id.in_(candidate_ids),
                StudentResponse.palette_status.in_(["answered", "answered_and_marked"]),
            )
            .all()
        }
        filtered = [q for q in candidates if q.id not in attempted_ids]
        random.shuffle(filtered)
        return filtered

    if selection_mode == "weak_topic":
        # Prioritize topics where the student has unresolved errors or low accuracy
        err_topic_ids = {
            q.topic_id
            for q in Question.query.join(
                ErrorNotebookEntry, ErrorNotebookEntry.question_id == Question.id
            )
            .filter(
                ErrorNotebookEntry.student_id == student_id,
                ErrorNotebookEntry.status == "unresolved",
            )
            .all()
            if q.topic_id
        }
        weak = [q for q in candidates if q.topic_id in err_topic_ids]
        other = [q for q in candidates if q.topic_id not in err_topic_ids]
        random.shuffle(weak)
        random.shuffle(other)
        return weak + other

    pool = list(candidates)
    random.shuffle(pool)
    return pool


def _balanced_subject_select(candidates: list[Question], limit: int) -> list[Question]:
    """Select questions balanced across chapters/topics using round-robin buckets."""
    buckets: dict[int, list[Question]] = {}
    for q in candidates:
        key = q.chapter_id or q.subject_id
        buckets.setdefault(key, []).append(q)

    selected: list[Question] = []
    keys = list(buckets.keys())
    idx = 0
    while len(selected) < limit and any(buckets.values()):
        key = keys[idx % len(keys)]
        if buckets[key]:
            selected.append(buckets[key].pop(0))
        idx += 1
    return selected


def generate_test(
    *,
    student_id: int,
    branch_id: int,
    exam_year: int,
    mode: str,
    subject_id: int | None = None,
    chapter_id: int | None = None,
    topic_id: int | None = None,
    concept_id: int | None = None,
    question_source: str = "MIXED",
    difficulty: str = "mixed",
    question_type: str = "ALL",
    selection_mode: str = "random",
    question_count: int = 10,
    duration_minutes: int | None = None,
) -> tuple[Test | None, str | None]:
    """Generate and persist a configured GATE assessment. Returns (Test, error_message)."""
    branch = Branch.query.get(branch_id)
    if not branch:
        return None, "Invalid GATE branch."

    syllabus_version = resolve_syllabus_version(branch_id, exam_year)
    pattern = get_exam_pattern(branch_id, exam_year)

    is_pattern_locked = mode == "full_mock"
    if is_pattern_locked:
        target_count = pattern.total_questions if pattern else 65
        target_duration = pattern.duration_minutes if pattern else 180
        question_type = "ALL"
        difficulty = "mixed"
    else:
        target_count = max(1, min(100, int(question_count or 10)))
        target_duration = (
            max(5, min(240, int(duration_minutes)))
            if duration_minutes
            else max(10, int(round(target_count * 2.5)))
        )

    candidates = _eligible_question_query(
        branch_id=branch_id,
        question_source=question_source,
        difficulty=difficulty,
        question_type=question_type,
        subject_id=None if is_pattern_locked else subject_id,
        chapter_id=None if is_pattern_locked else chapter_id,
        topic_id=None if is_pattern_locked else topic_id,
        concept_id=None if is_pattern_locked else concept_id,
    ).all()

    ordered = _apply_selection_mode(
        candidates, student_id=student_id, selection_mode=selection_mode
    )

    if not ordered:
        return (
            None,
            "No verified questions match your selected filters yet. Try switching Question Source to 'Mixed' or broadening the scope.",
        )

    if is_pattern_locked:
        ga_qs = [q for q in ordered if q.subject and q.subject.is_general_aptitude][:10]
        tech_qs = [q for q in ordered if not (q.subject and q.subject.is_general_aptitude)][:55]
        chosen = ga_qs + tech_qs
        if not chosen:
            chosen = ordered[:target_count]
    elif mode in ("subject", "chapter") and selection_mode == "random":
        chosen = _balanced_subject_select(ordered, target_count)
    else:
        chosen = ordered[:target_count]

    scope_label = branch.code
    if concept_id and (c := Concept.query.get(concept_id)):
        scope_label = f"{branch.code} · {c.name}"
    elif topic_id and (t := Topic.query.get(topic_id)):
        scope_label = f"{branch.code} · {t.name}"
    elif chapter_id and (ch := Chapter.query.get(chapter_id)):
        scope_label = f"{branch.code} · {ch.name}"
    elif subject_id and (s := Subject.query.get(subject_id)):
        scope_label = f"{branch.code} · {s.name}"

    mode_titles = {
        "concept": f"Concept Test: {scope_label}",
        "chapter": f"Chapter Test: {scope_label}",
        "subject": f"Subject Test: {scope_label}",
        "full_mock": f"GATE {exam_year} {branch.code} Full-Length Mock",
        "daily_challenge": f"Daily Challenge ({branch.code}) – {date.today().isoformat()}",
        "reattempt": f"Reattempt Practice ({selection_mode.title()}) – {branch.code}",
    }

    config = TestConfiguration(
        user_id=student_id,
        branch_id=branch_id,
        syllabus_version_id=syllabus_version.id if syllabus_version else None,
        mode=mode,
        target_scope_json={
            "subject_id": subject_id,
            "chapter_id": chapter_id,
            "topic_id": topic_id,
            "concept_id": concept_id,
        },
        question_source=question_source,
        difficulty=difficulty,
        question_type=question_type,
        selection_mode=selection_mode,
        question_count=len(chosen),
        duration_minutes=target_duration,
        is_pattern_locked=is_pattern_locked,
    )
    db.session.add(config)
    db.session.flush()

    total_marks = sum(float(q.marks) for q in chosen)
    test = Test(
        configuration_id=config.id,
        title=mode_titles.get(mode, f"GATE Assessment – {branch.code}"),
        branch_id=branch_id,
        exam_pattern_id=pattern.id if (is_pattern_locked and pattern) else None,
        total_marks=total_marks,
        duration_minutes=target_duration,
        is_daily_challenge=(mode == "daily_challenge"),
        challenge_date=date.today() if mode == "daily_challenge" else None,
    )
    db.session.add(test)
    db.session.flush()

    for idx, q in enumerate(chosen, start=1):
        sec = "General Aptitude" if (q.subject and q.subject.is_general_aptitude) else "Technical"
        db.session.add(
            TestQuestion(
                test_id=test.id,
                question_id=q.id,
                order_index=idx,
                section_name=sec,
            )
        )

    db.session.commit()
    return test, None


def get_or_create_daily_challenge(student_id: int, branch_id: int, exam_year: int) -> tuple[Test | None, str | None]:
    """Return today's Daily Challenge for the branch, or generate one deterministically."""
    today = date.today()
    existing = (
        Test.query.filter_by(branch_id=branch_id, is_daily_challenge=True, challenge_date=today)
        .order_by(Test.id.desc())
        .first()
    )
    if existing:
        return existing, None

    return generate_test(
        student_id=student_id,
        branch_id=branch_id,
        exam_year=exam_year,
        mode="daily_challenge",
        question_source="MIXED",
        difficulty="mixed",
        question_type="ALL",
        selection_mode="random",
        question_count=10,
        duration_minutes=20,
    )
