"""Pytest configuration and isolated test fixtures for GATE Intelligence."""

import pytest

from app import create_app
from app.extensions import db
from app.models.syllabus import Branch, Chapter, Concept, Subject, Topic
from app.services.question_service import create_question_record
from app.services.syllabus_service import resolve_syllabus_version
from scripts.seed_all import run_all_seeds


def _seed_test_only_questions() -> None:
    """Create isolated test-fixture questions (PYQ/AI_GENERATED) for automated tests only."""
    cs = Branch.query.filter_by(code="CS").first()
    sv = resolve_syllabus_version(cs.id, 2026)
    ga = Subject.query.filter_by(syllabus_version_id=sv.id, code="GA").first()
    os_subj = Subject.query.filter_by(syllabus_version_id=sv.id, code="CS-OS").first()
    dbms_subj = Subject.query.filter_by(syllabus_version_id=sv.id, code="CS-DBMS").first()
    cn_subj = Subject.query.filter_by(syllabus_version_id=sv.id, code="CS-CN").first()

    ga_ch = ga.chapters[0]
    ga_tp = ga_ch.topics[0]
    os_ch = os_subj.chapters[0]
    os_tp = os_ch.topics[1]
    os_cp = os_tp.concepts[0]
    dbms_ch = dbms_subj.chapters[0]
    dbms_tp = dbms_ch.topics[1]
    cn_ch = cn_subj.chapters[0]
    cn_tp = cn_ch.topics[1]

    create_question_record(
        branch_id=cs.id,
        subject_id=ga.id,
        chapter_id=ga_ch.id,
        topic_id=ga_tp.id,
        concept_id=ga_tp.concepts[0].id,
        source_type="PYQ",
        question_type="MCQ",
        marks=1,
        difficulty="easy",
        statement_md="Test fixture GA MCQ: +25% followed by -20% yields what net percentage change?",
        options=[
            {"label": "A", "text": "+5%", "is_correct": False},
            {"label": "B", "text": "0%", "is_correct": True},
            {"label": "C", "text": "-5%", "is_correct": False},
            {"label": "D", "text": "-1%", "is_correct": False},
        ],
        correct_answer_json={"option": "B"},
        explanation_json={"concept_explanation": "1.25 * 0.80 = 1.00."},
        exam_year=2024,
        original_question_number="1",
        page_number=1,
        attribution_text="Test Fixture PYQ",
    )
    create_question_record(
        branch_id=cs.id,
        subject_id=os_subj.id,
        chapter_id=os_ch.id,
        topic_id=os_tp.id,
        concept_id=os_cp.id,
        source_type="PYQ",
        question_type="NAT",
        marks=2,
        difficulty="medium",
        statement_md="Test fixture OS NAT: 3 processes each needing max 2 instances require how many minimum instances?",
        correct_answer_json={"value": 4},
        nat_min=4.0,
        nat_max=4.0,
        explanation_json={"formula_used": "N*(M-1)+1 = 4"},
        exam_year=2024,
        original_question_number="2",
        page_number=1,
        attribution_text="Test Fixture PYQ",
    )
    create_question_record(
        branch_id=cs.id,
        subject_id=dbms_subj.id,
        chapter_id=dbms_ch.id,
        topic_id=dbms_tp.id,
        concept_id=dbms_tp.concepts[0].id,
        source_type="AI_GENERATED",
        question_type="MSQ",
        marks=2,
        difficulty="medium",
        statement_md="Test fixture DBMS MSQ: Which statements hold for normal forms?",
        options=[
            {"label": "A", "text": "Every BCNF relation is in 3NF.", "is_correct": True},
            {"label": "B", "text": "3NF preserves dependencies.", "is_correct": True},
            {"label": "C", "text": "BCNF always preserves dependencies.", "is_correct": False},
            {"label": "D", "text": "2-attribute relations are in BCNF.", "is_correct": True},
        ],
        correct_answer_json={"options": ["A", "B", "D"]},
        explanation_json={"concept_explanation": "BCNF => 3NF."},
    )
    create_question_record(
        branch_id=cs.id,
        subject_id=cn_subj.id,
        chapter_id=cn_ch.id,
        topic_id=cn_tp.id,
        concept_id=cn_tp.concepts[0].id,
        source_type="PYQ",
        question_type="NAT",
        marks=2,
        difficulty="easy",
        statement_md="Test fixture CN NAT: Usable hosts in /26 IPv4 subnet?",
        correct_answer_json={"value": 62},
        nat_min=62.0,
        nat_max=62.0,
        explanation_json={"formula_used": "2^6 - 2 = 62"},
        exam_year=2023,
        original_question_number="3",
        page_number=2,
        attribution_text="Test Fixture PYQ",
    )
    create_question_record(
        branch_id=cs.id,
        subject_id=os_subj.id,
        chapter_id=os_ch.id,
        topic_id=os_tp.id,
        concept_id=os_cp.id,
        source_type="AI_GENERATED",
        question_type="MCQ",
        marks=2,
        difficulty="hard",
        statement_md="Test fixture OS MCQ: Which scheduling algorithm may cause starvation?",
        options=[
            {"label": "A", "text": "FCFS", "is_correct": False},
            {"label": "B", "text": "Round Robin", "is_correct": False},
            {"label": "C", "text": "Shortest Job First", "is_correct": True},
            {"label": "D", "text": "FIFO", "is_correct": False},
        ],
        correct_answer_json={"option": "C"},
        explanation_json={"concept_explanation": "Long jobs can starve under SJF."},
    )
    db.session.commit()


@pytest.fixture()
def app(tmp_path):
    """Create application configured for automated testing."""
    application = create_app("testing")
    application.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    with application.app_context():
        db.drop_all()
        db.create_all()
        run_all_seeds()
        _seed_test_only_questions()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()
