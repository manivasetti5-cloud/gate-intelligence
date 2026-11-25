"""End-to-end 9-step automatic GATE PDF extraction, classification, solving, and verification pipeline."""

from datetime import datetime, timezone
from pathlib import Path

from flask import current_app

from app.extensions import db
from app.models.paper import (
    ExtractedQuestion,
    ExtractionJob,
    ExtractionLog,
    Paper,
    PaperVersion,
)
from app.models.question import QuestionImage
from app.services.answer_solver import solve_question_with_ai
from app.services.answer_verifier import verify_proposed_answer
from app.services.duplicate_detector import compute_image_dhash, find_duplicate_question
from app.services.ocr_service import run_ocr_on_image
from app.services.pdf_extractor import extract_pdf_document
from app.services.question_classifier import classify_question_to_syllabus
from app.services.question_segmenter import segment_pages_into_questions
from app.services.question_service import create_question_record


def _update_job(job: ExtractionJob, status: str, progress: int, message: str, stage: str, level: str = "INFO") -> None:
    job.status = status
    job.progress_percent = progress
    db.session.add(
        ExtractionLog(
            job_id=job.id,
            stage=stage,
            level=level,
            message=message,
        )
    )
    db.session.commit()


def process_extraction_job(job_id: int) -> ExtractionJob:
    """Run the automatic PDF processing pipeline for an ExtractionJob."""
    job = ExtractionJob.query.get_or_404(job_id)
    pv: PaperVersion = job.paper_version
    paper: Paper = pv.paper

    job.started_at = datetime.now(timezone.utc)
    db.session.commit()

    static_root = Path(current_app.root_path) / "static"
    pdf_abs_path = static_root / pv.file_path
    out_dir = Path(current_app.config["UPLOAD_FOLDER"]) / "extracted" / f"job_{job.id}"

    try:
        # Step 2: PDF Extraction
        _update_job(job, "extracting", 15, f"Extracting text and embedded figures from {pdf_abs_path.name}.", "extract")
        extracted = extract_pdf_document(pdf_abs_path, out_dir, static_root)
        pv.page_count = extracted["page_count"]
        pages = extracted["pages"]
        _update_job(job, "extracting", 25, f"Extracted {pv.page_count} pages via {extracted['backend']}.", "extract")

        # Step 3: OCR Processing for low-text pages
        _update_job(job, "ocr_processing", 35, "Checking pages for scanned content requiring OCR.", "ocr")
        for pg in pages:
            if len((pg.text or "").strip()) < 40 and pg.image_paths:
                for rel_img in pg.image_paths:
                    ocr_text, ok, note = run_ocr_on_image(static_root / rel_img)
                    if ok and ocr_text:
                        pg.text = (pg.text + "\n" + ocr_text).strip()
                        pg.used_ocr = True
                    elif note:
                        db.session.add(
                            ExtractionLog(job_id=job.id, stage="ocr", level="WARNING", message=f"Page {pg.page_number}: {note}")
                        )
        db.session.commit()

        # Step 3 & 4: Question Segmentation & Diagram Preservation
        _update_job(job, "segmenting", 50, "Segmenting questions, options, marks, and attaching diagrams.", "segment")
        segments = segment_pages_into_questions(pages)
        job.total_detected = len(segments)
        db.session.commit()

        if not segments:
            _update_job(
                job,
                "requires_review",
                100,
                "No numbered GATE questions (e.g. 'Q.1 ...') were detected automatically. Manual review required.",
                "segment",
                level="WARNING",
            )
            job.completed_at = datetime.now(timezone.utc)
            db.session.commit()
            return job

        published_count = 0
        review_count = 0
        failed_count = 0

        # Steps 5, 6, 7, 8, 9 per segmented question
        for idx, seg in enumerate(segments, start=1):
            try:
                _update_job(
                    job,
                    "classifying",
                    55 + int((idx / len(segments)) * 10),
                    f"Classifying Q.{seg['raw_q_number']} into GATE syllabus.",
                    "classify",
                )
                cls = classify_question_to_syllabus(
                    branch_id=paper.branch_id,
                    exam_year=paper.exam_year,
                    statement_md=seg["statement_md"],
                    question_type=seg["question_type"],
                )

                _update_job(
                    job,
                    "solving",
                    68 + int((idx / len(segments)) * 10),
                    f"Generating solution for Q.{seg['raw_q_number']}.",
                    "solve",
                )
                solved = solve_question_with_ai(
                    statement_md=seg["statement_md"],
                    question_type=seg["question_type"],
                    options=seg["options"],
                    marks=seg["marks"],
                )

                _update_job(
                    job,
                    "verifying",
                    80 + int((idx / len(segments)) * 10),
                    f"Running independent verification for Q.{seg['raw_q_number']}.",
                    "verify",
                )
                ver = verify_proposed_answer(
                    statement_md=seg["statement_md"],
                    question_type=seg["question_type"],
                    proposed_answer_json=solved["correct_answer_json"],
                    options=seg["options"],
                    verification_expression=solved.get("verification_expression", ""),
                    primary_confidence=solved["confidence"],
                )

                _update_job(
                    job,
                    "duplicate_checking",
                    92,
                    f"Checking Q.{seg['raw_q_number']} for duplicates.",
                    "dedup",
                )
                dup = find_duplicate_question(
                    branch_id=paper.branch_id, statement_md=seg["statement_md"]
                )

                first_img = seg["image_paths"][0] if seg["image_paths"] else None
                ext_q = ExtractedQuestion(
                    job_id=job.id,
                    page_number=seg["page_number"],
                    raw_q_number=seg["raw_q_number"],
                    raw_text=seg["raw_text"],
                    crop_image_path=first_img,
                    structured_json={
                        "statement_md": seg["statement_md"],
                        "options": seg["options"],
                        "question_type": seg["question_type"],
                        "marks": seg["marks"],
                        "classification": cls,
                        "solved": solved,
                        "verification": ver,
                        "duplicate": dup,
                        "image_paths": seg["image_paths"],
                    },
                    duplicate_of_question_id=dup["matched_question_id"],
                    confidence_score=min(seg["confidence_score"], cls["confidence"]),
                    review_status="pending",
                )
                db.session.add(ext_q)
                db.session.flush()

                if dup["is_duplicate"]:
                    ext_q.review_status = "rejected"
                    review_count += 1
                    continue

                # Only auto-publish if verified AND syllabus subject resolved
                auto_publish = ver["verification_status"] == "verified" and cls["subject_id"] is not None
                if cls["subject_id"] is not None:
                    # Mark matching options if MCQ/MSQ
                    opts_with_flags = []
                    corr = solved["correct_answer_json"]
                    for o in seg["options"]:
                        lbl = o["label"].upper()
                        is_corr = False
                        if seg["question_type"] == "MCQ":
                            is_corr = lbl == str(corr.get("option", "")).upper()
                        elif seg["question_type"] == "MSQ":
                            is_corr = lbl in {str(x).upper() for x in corr.get("options", [])}
                        opts_with_flags.append({"label": lbl, "text": o["text"], "is_correct": is_corr})

                    q = create_question_record(
                        branch_id=paper.branch_id,
                        subject_id=cls["subject_id"],
                        chapter_id=cls["chapter_id"],
                        topic_id=cls["topic_id"],
                        concept_id=cls["concept_id"],
                        source_type="PYQ",
                        question_type=seg["question_type"],
                        marks=seg["marks"],
                        difficulty=cls["difficulty"],
                        statement_md=seg["statement_md"],
                        correct_answer_json=solved["correct_answer_json"],
                        explanation_json=solved["explanation_json"],
                        options=opts_with_flags,
                        nat_min=solved.get("nat_min"),
                        nat_max=solved.get("nat_max"),
                        exam_year=paper.exam_year,
                        shift_session=paper.shift,
                        original_question_number=seg["raw_q_number"],
                        page_number=seg["page_number"],
                        attribution_text=f"{paper.title} (Q.{seg['raw_q_number']}, p.{seg['page_number']})",
                        paper_id=paper.id,
                        verification_status=ver["verification_status"],
                        is_published=auto_publish,
                        tags=[seg["question_type"], f"GATE-{paper.exam_year}"],
                        verifier_type=ver["verifier_type"],
                        verifier_tool=ver["model_or_tool"],
                    )
                    db.session.flush()
                    for img_rel in seg["image_paths"]:
                        dhash = compute_image_dhash(static_root / img_rel)
                        db.session.add(
                            QuestionImage(
                                question_id=q.id,
                                file_path=img_rel,
                                caption=f"Page {seg['page_number']} figure",
                                image_type="page_crop",
                                perceptual_hash=dhash,
                            )
                        )
                    ext_q.linked_question_id = q.id
                    ext_q.review_status = "published" if auto_publish else "pending"

                if auto_publish:
                    published_count += 1
                else:
                    review_count += 1

                db.session.commit()
            except Exception as q_err:
                failed_count += 1
                db.session.add(
                    ExtractionLog(
                        job_id=job.id,
                        stage="question_process",
                        level="ERROR",
                        message=f"Q.{seg.get('raw_q_number')} failed: {q_err}",
                    )
                )
                db.session.commit()

        job.published_count = published_count
        job.review_count = review_count
        job.failed_count = failed_count
        final_status = "completed" if (review_count == 0 and failed_count == 0) else "requires_review"
        job.completed_at = datetime.now(timezone.utc)
        _update_job(
            job,
            final_status,
            100,
            f"Pipeline finished: {published_count} published, {review_count} awaiting review, {failed_count} failed.",
            "complete",
        )
        return job

    except Exception as exc:
        job.error_message = str(exc)
        job.completed_at = datetime.now(timezone.utc)
        _update_job(job, "failed", 100, f"Pipeline error: {exc}", "error", level="ERROR")
        return job
