"""Import authorized historical GATE PYQ datasets from verified JSON files."""

import argparse
import json
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models.question import Question
from app.models.syllabus import Branch, Chapter, Concept, Subject, Topic
from app.services.question_service import compute_normalized_hash, create_question_record
from app.services.syllabus_service import resolve_syllabus_version


def import_pyq_json(json_path: str | Path) -> dict:
    """
    Import verified PYQ records from a JSON file.
    Expected schema: {"paper_title": ..., "branch_code": "CS", "exam_year": 2024, "questions": [...]}
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"PYQ dataset file not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    branch_code = payload["branch_code"].upper()
    exam_year = int(payload["exam_year"])
    branch = Branch.query.filter_by(code=branch_code).first()
    if not branch:
        raise ValueError(f"Unknown branch code: {branch_code}")

    sv = resolve_syllabus_version(branch.id, exam_year)
    if not sv:
        raise ValueError(f"No syllabus version found for {branch_code} {exam_year}")

    imported = 0
    skipped_duplicates = 0

    for item in payload.get("questions", []):
        norm_hash = compute_normalized_hash(item["statement_md"])
        if Question.query.filter_by(branch_id=branch.id, normalized_hash=norm_hash).first():
            skipped_duplicates += 1
            continue

        subj = Subject.query.filter_by(
            syllabus_version_id=sv.id, code=item["subject_code"]
        ).first()
        if not subj:
            subj = Subject.query.filter_by(syllabus_version_id=sv.id).first()

        chapter = (
            Chapter.query.filter_by(subject_id=subj.id, name=item.get("chapter_name")).first()
            if (subj and item.get("chapter_name"))
            else None
        )
        topic = (
            Topic.query.filter_by(chapter_id=chapter.id, name=item.get("topic_name")).first()
            if (chapter and item.get("topic_name"))
            else None
        )
        concept = (
            Concept.query.filter_by(topic_id=topic.id, name=item.get("concept_name")).first()
            if (topic and item.get("concept_name"))
            else None
        )

        create_question_record(
            branch_id=branch.id,
            subject_id=subj.id,
            chapter_id=chapter.id if chapter else None,
            topic_id=topic.id if topic else None,
            concept_id=concept.id if concept else None,
            source_type="PYQ",
            question_type=item["question_type"],
            marks=int(item["marks"]),
            difficulty=item.get("difficulty", "medium"),
            statement_md=item["statement_md"],
            correct_answer_json=item["correct_answer_json"],
            explanation_json=item.get("explanation_json", {}),
            options=item.get("options"),
            nat_min=item.get("nat_min"),
            nat_max=item.get("nat_max"),
            exam_year=exam_year,
            shift_session=item.get("shift_session"),
            original_question_number=item.get("original_question_number"),
            page_number=item.get("page_number"),
            attribution_text=item.get("attribution_text") or payload.get("paper_title"),
            verification_status=item.get("verification_status", "verified"),
            is_published=item.get("verification_status", "verified") == "verified",
            tags=item.get("tags", []),
            verifier_type="official_key",
            verifier_tool="authorized_pyq_import",
        )
        imported += 1

    db.session.commit()
    return {"imported": imported, "skipped_duplicates": skipped_duplicates}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import authorized GATE PYQ JSON dataset.")
    parser.add_argument("--file", required=True, help="Path to authorized PYQ JSON file.")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        result = import_pyq_json(args.file)
        print("PYQ Import Result:", result)
