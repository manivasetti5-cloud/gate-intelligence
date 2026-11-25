"""Original syllabus-aligned GATE question generation with strict validation and verification."""

from datetime import datetime, timezone
from typing import Any

from app.extensions import db
from app.models.paper import GeneratedQuestion, GenerationJob, GenerationLog
from app.models.syllabus import Branch, Chapter, Concept, Subject, Topic
from app.services.answer_verifier import verify_proposed_answer
from app.services.duplicate_detector import find_duplicate_question
from app.services.llm_client import (
    LLMSchemaError,
    LLMUnavailableError,
    generate_structured_json,
)
from app.services.question_service import create_question_record
from app.services.syllabus_service import resolve_syllabus_version


def _log_gen(job_id: int, message: str, level: str = "INFO", meta: dict | None = None) -> None:
    db.session.add(
        GenerationLog(
            job_id=job_id,
            level=level,
            message=message,
            metadata_json=meta or {},
        )
    )
    db.session.commit()


def run_generation_job(job_id: int) -> GenerationJob:
    """Execute an AI original question generation job and verify every output before saving."""
    job = GenerationJob.query.get_or_404(job_id)
    job.status = "running"
    db.session.commit()

    branch = Branch.query.get(job.branch_id)
    sv = resolve_syllabus_version(job.branch_id, 2026)
    subj = Subject.query.get(job.subject_id) if job.subject_id else (
        Subject.query.filter_by(syllabus_version_id=sv.id).first() if sv else None
    )
    chap = Chapter.query.get(job.chapter_id) if job.chapter_id else (
        subj.chapters[0] if (subj and subj.chapters) else None
    )
    topic = Topic.query.get(job.topic_id) if job.topic_id else (
        chap.topics[0] if (chap and chap.topics) else None
    )
    concept = Concept.query.get(job.concept_id) if job.concept_id else (
        topic.concepts[0] if (topic and topic.concepts) else None
    )

    if not branch or not subj:
        job.status = "failed"
        _log_gen(job.id, "Branch or subject could not be resolved.", level="ERROR")
        return job

    created_count = 0
    for idx in range(1, job.target_count + 1):
        prompt = (
            "Create 1 original, non-copied GATE-level examination question.\n"
            f"Branch: {branch.code} ({branch.name})\n"
            f"Subject: {subj.name}\n"
            f"Chapter: {chap.name if chap else 'General'}\n"
            f"Topic: {topic.name if topic else 'General'}\n"
            f"Concept: {concept.name if concept else 'Core Principles'}\n"
            "Vary between MCQ (1 or 2 marks), MSQ (2 marks), and NAT (1 or 2 marks).\n"
            "Return strict JSON with keys:\n"
            "{\n"
            '  "question_type": "MCQ|MSQ|NAT",\n'
            '  "marks": 1 or 2,\n'
            '  "difficulty": "easy|medium|hard",\n'
            '  "statement_md": "...",\n'
            '  "options": [{"label":"A","text":"...","is_correct":false}, ...] (empty list for NAT),\n'
            '  "correct_answer": <"A" or ["A","C"] or 12.5>,\n'
            '  "nat_min": <float or null>,\n'
            '  "nat_max": <float or null>,\n'
            '  "verification_expression": "<optional arithmetic expression>",\n'
            '  "explanation": {\n'
            '    "concept_explanation": "...",\n'
            '    "step_by_step": "...",\n'
            '    "formula_used": "...",\n'
            '    "shortcut_method": "...",\n'
            '    "alternative_method": "...",\n'
            '    "common_mistakes": "...",\n'
            '    "option_analysis": "...",\n'
            '    "gate_tip": "..."\n'
            "  }\n"
            "}"
        )
        try:
            parsed, model_used = generate_structured_json(
                prompt,
                required_keys=[
                    "question_type",
                    "marks",
                    "difficulty",
                    "statement_md",
                    "correct_answer",
                    "explanation",
                ],
            )
            qtype = str(parsed["question_type"]).upper()
            if qtype not in ("MCQ", "MSQ", "NAT"):
                raise LLMSchemaError(f"Unsupported question_type: {qtype}")

            marks = 2 if int(parsed["marks"]) == 2 else 1
            diff = str(parsed["difficulty"]).lower()
            if diff not in ("easy", "medium", "hard"):
                diff = "medium"

            dup = find_duplicate_question(branch_id=branch.id, statement_md=parsed["statement_md"])
            if dup["is_duplicate"]:
                _log_gen(job.id, f"Skipped duplicate candidate #{idx} (matched Q#{dup['matched_question_id']}).", level="WARNING")
                continue

            ans = parsed["correct_answer"]
            if qtype == "MCQ":
                correct_json = {"option": str(ans).strip().upper()[:1]}
            elif qtype == "MSQ":
                correct_json = {"options": sorted({str(x).strip().upper()[:1] for x in (ans if isinstance(ans, list) else [ans])})}
            else:
                correct_json = {"value": float(ans)}

            options = parsed.get("options") if qtype in ("MCQ", "MSQ") else []
            ver = verify_proposed_answer(
                statement_md=parsed["statement_md"],
                question_type=qtype,
                proposed_answer_json=correct_json,
                options=options,
                verification_expression=parsed.get("verification_expression", ""),
                primary_confidence=0.82,
            )

            is_verified = ver["verification_status"] == "verified"
            q = create_question_record(
                branch_id=branch.id,
                subject_id=subj.id,
                chapter_id=chap.id if chap else None,
                topic_id=topic.id if topic else None,
                concept_id=concept.id if concept else None,
                source_type="AI_GENERATED",
                question_type=qtype,
                marks=marks,
                difficulty=diff,
                statement_md=parsed["statement_md"],
                correct_answer_json=correct_json,
                explanation_json=parsed.get("explanation", {}),
                options=options,
                nat_min=parsed.get("nat_min"),
                nat_max=parsed.get("nat_max"),
                exam_year=2026,
                attribution_text=f"AI-Generated Original Question ({model_used}, prompt {job.prompt_version})",
                verification_status=ver["verification_status"],
                is_published=is_verified,
                tags=[branch.code, subj.code, qtype, "ai-generated"],
                verifier_type=ver["verifier_type"],
                verifier_tool=ver["model_or_tool"],
            )
            db.session.flush()

            db.session.add(
                GeneratedQuestion(
                    job_id=job.id,
                    question_id=q.id,
                    model_used=model_used,
                    prompt_version=job.prompt_version,
                    schema_valid=True,
                    verification_passed=is_verified,
                    quality_score=ver["confidence_score"],
                )
            )
            db.session.commit()
            created_count += 1
            _log_gen(
                job.id,
                f"Generated Q#{q.id} ({qtype}, {marks}M) -> status: {ver['verification_status']}.",
            )
        except LLMUnavailableError as exc:
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
            _log_gen(job.id, f"LLM unavailable: {exc}", level="ERROR")
            return job
        except (LLMSchemaError, ValueError, TypeError) as exc:
            _log_gen(job.id, f"Candidate #{idx} failed schema validation: {exc}", level="WARNING")
            continue

    job.status = "completed"
    job.completed_at = datetime.now(timezone.utc)
    _log_gen(job.id, f"Generation job completed with {created_count} questions stored.")
    return job
