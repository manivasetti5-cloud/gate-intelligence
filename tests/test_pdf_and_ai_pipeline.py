"""Phase 3 tests: PDF upload & extraction pipeline, SymPy verifier, deduplication, and AI generation."""

import io

from app.extensions import db
from app.models.paper import ExtractedQuestion, ExtractionJob, GenerationJob
from app.models.question import Question
from app.models.syllabus import Branch, Subject
from app.services.ai_question_generator import run_generation_job
from app.services.answer_verifier import verify_proposed_answer
from app.services.duplicate_detector import find_duplicate_question


def _build_minimal_pdf(text_lines: list[str]) -> bytes:
    """Create a valid single-page PDF containing readable text lines without external binaries."""
    escaped = []
    for idx, line in enumerate(text_lines):
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        dy = -16 if idx > 0 else 0
        escaped.append(f"0 {dy} Td ({safe}) Tj")
    stream_body = "BT /F1 11 Tf 50 750 Td\n" + "\n".join(escaped) + "\nET"
    stream_bytes = stream_body.encode("latin-1")

    objs = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n",
        f"4 0 obj << /Length {len(stream_bytes)} >> stream\n".encode("latin-1")
        + stream_bytes
        + b"\nendstream endobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("latin-1"))
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("latin-1"))
    out.extend(
        f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("latin-1")
    )
    return bytes(out)


def test_sympy_verifier_and_duplicate_detector(app):
    with app.app_context():
        # SymPy verifier catches exact match vs wrong proposed answer
        ok_res = verify_proposed_answer(
            statement_md="Compute 12 * 5 + 4.",
            question_type="NAT",
            proposed_answer_json={"value": 64},
            verification_expression="12 * 5 + 4",
            primary_confidence=0.9,
        )
        assert ok_res["verification_status"] == "verified"
        assert ok_res["is_match"] is True

        bad_res = verify_proposed_answer(
            statement_md="Compute 12 * 5 + 4.",
            question_type="NAT",
            proposed_answer_json={"value": 99},
            verification_expression="12 * 5 + 4",
            primary_confidence=0.9,
        )
        assert bad_res["verification_status"] == "needs_manual_review"
        assert bad_res["is_match"] is False

        # Duplicate detector catches seeded question via normalized hash / TF-IDF
        cs = Branch.query.filter_by(code="CS").first()
        q = Question.query.filter_by(branch_id=cs.id).first()
        dup = find_duplicate_question(branch_id=cs.id, statement_md=q.statement_md)
        assert dup["is_duplicate"] is True
        assert dup["matched_question_id"] == q.id


def test_admin_pdf_upload_extraction_and_verification_queue(client, app):
    # Sign in as admin
    client.post(
        "/auth/admin/login",
        data={"email": "admin@gateintelligence.local", "password": "Admin@Gate2026!"},
        follow_redirects=True,
    )

    with app.app_context():
        cs_id = Branch.query.filter_by(code="CS").first().id

    pdf_bytes = _build_minimal_pdf(
        [
            "Q.1 [1 Mark] Which data structure follows LIFO order?",
            "(A) Queue",
            "(B) Stack",
            "(C) Heap",
            "(D) Graph",
            "Q.2 [2 Marks] [NAT] Compute the value of 15 * 4 + 2.",
        ]
    )

    resp = client.post(
        "/admin/upload-paper",
        data={
            "branch_id": str(cs_id),
            "exam_year": "2024",
            "title": "Synthetic CS Test Paper",
            "pdf_file": (io.BytesIO(pdf_bytes), "synthetic_cs_2024.pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Extraction Job #" in resp.data

    with app.app_context():
        job = ExtractionJob.query.order_by(ExtractionJob.id.desc()).first()
        assert job is not None
        assert job.total_detected == 2
        assert ExtractedQuestion.query.filter_by(job_id=job.id).count() == 2
        # Q.2 should be auto-solved and SymPy-verified!
        assert job.published_count >= 1
        # Q.1 (without LLM key) should sit in review queue, never auto-published!
        assert job.review_count >= 1

    # Admin verifies Q.1 in verification queue
    ver_page = client.get("/admin/verification")
    assert ver_page.status_code == 200
    assert b"LIFO" in ver_page.data

    with app.app_context():
        pending_q = Question.query.filter(Question.verification_status != "verified").first()
        pending_id = pending_q.id

    approve = client.post(
        "/admin/verification",
        data={
            "question_id": str(pending_id),
            "action": "approve_publish",
            "override_answer": "B",
        },
        follow_redirects=True,
    )
    assert approve.status_code == 200
    with app.app_context():
        q = Question.query.get(pending_id)
        assert q.verification_status == "verified"
        assert q.is_published is True


def test_ai_question_generator_with_mocked_llm(app, monkeypatch):
    def fake_llm(prompt, **kwargs):
        if "Independently verify" in prompt:
            return {"independent_answer": 42, "confidence": 0.95}, "mock-verifier"
        return {
            "question_type": "NAT",
            "marks": 2,
            "difficulty": "medium",
            "statement_md": "Evaluate the determinant of a 2x2 diagonal matrix with entries 6 and 7.",
            "options": [],
            "correct_answer": 42,
            "nat_min": 42.0,
            "nat_max": 42.0,
            "verification_expression": "6 * 7",
            "explanation": {
                "concept_explanation": "Determinant of diagonal matrix is product of diagonal elements.",
                "step_by_step": "6 * 7 = 42.",
                "formula_used": "det(diag(a, b)) = a * b",
                "shortcut_method": "Multiply diagonal entries.",
                "alternative_method": "ad - bc = 6*7 - 0 = 42.",
                "common_mistakes": "Adding instead of multiplying.",
                "option_analysis": "NAT",
                "gate_tip": "Applies to any triangular matrix as well.",
            },
        }, "mock-generator"

    monkeypatch.setattr("app.services.ai_question_generator.generate_structured_json", fake_llm)
    monkeypatch.setattr("app.services.answer_verifier.is_llm_configured", lambda: True)
    monkeypatch.setattr("app.services.answer_verifier.generate_structured_json", fake_llm)

    with app.app_context():
        cs = Branch.query.filter_by(code="CS").first()
        subj = Subject.query.filter(Subject.code == "CS-EM").first()
        job = GenerationJob(
            branch_id=cs.id,
            subject_id=subj.id,
            target_count=1,
            status="queued",
        )
        db.session.add(job)
        db.session.commit()

        done_job = run_generation_job(job.id)
        assert done_job.status == "completed"
        assert len(done_job.generated_items) == 1
        gen_q = done_job.generated_items[0]
        assert gen_q.verification_passed is True
        assert gen_q.question.source.source_type == "AI_GENERATED"
        assert gen_q.question.is_published is True
