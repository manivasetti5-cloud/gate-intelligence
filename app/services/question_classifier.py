"""AI and syllabus-keyword classification for extracted GATE questions."""

from typing import Any

from app.models.syllabus import Chapter, Concept, Subject, Topic
from app.services.llm_client import (
    LLMSchemaError,
    LLMUnavailableError,
    generate_structured_json,
    is_llm_configured,
)
from app.services.syllabus_service import get_syllabus_tree, resolve_syllabus_version


def _keyword_classify(statement: str, subjects: list[Subject]) -> dict[str, Any]:
    """Deterministic fallback classification against syllabus names using keyword overlap."""
    text_l = (statement or "").lower()
    best_subj = subjects[0] if subjects else None
    best_ch = None
    best_tp = None
    best_cp = None
    best_score = -1

    for subj in subjects:
        for ch in subj.chapters:
            for tp in ch.topics:
                for cp in tp.concepts:
                    tokens = set((f"{subj.name} {ch.name} {tp.name} {cp.name}").lower().split())
                    score = sum(1 for tok in tokens if len(tok) > 3 and tok in text_l)
                    if score > best_score:
                        best_score = score
                        best_subj, best_ch, best_tp, best_cp = subj, ch, tp, cp

    return {
        "subject_id": best_subj.id if best_subj else None,
        "chapter_id": best_ch.id if best_ch else None,
        "topic_id": best_tp.id if best_tp else None,
        "concept_id": best_cp.id if best_cp else None,
        "difficulty": "medium",
        "confidence": 0.45 if best_score <= 0 else min(0.8, 0.5 + 0.08 * best_score),
        "method": "keyword_fallback",
    }


def classify_question_to_syllabus(
    *,
    branch_id: int,
    exam_year: int,
    statement_md: str,
    question_type: str,
) -> dict[str, Any]:
    """Classify a question into Branch -> Subject -> Chapter -> Topic -> Concept and difficulty."""
    sv = resolve_syllabus_version(branch_id, exam_year)
    subjects = get_syllabus_tree(sv.id) if sv else []
    if not subjects:
        return {
            "subject_id": None,
            "chapter_id": None,
            "topic_id": None,
            "concept_id": None,
            "difficulty": "medium",
            "confidence": 0.2,
            "method": "no_syllabus",
        }

    if is_llm_configured():
        catalog = []
        for s in subjects:
            for ch in s.chapters:
                for tp in ch.topics:
                    catalog.append(f"subject={s.name} | chapter={ch.name} | topic={tp.name}")
        prompt = (
            "Classify this GATE question into the closest Subject, Chapter, Topic, and Difficulty.\n"
            f"Question Type: {question_type}\n"
            f"Question:\n{statement_md}\n\n"
            "Allowed Syllabus Catalog:\n" + "\n".join(catalog[:80]) + "\n\n"
            'Return JSON: {"subject": "...", "chapter": "...", "topic": "...", '
            '"difficulty": "easy|medium|hard", "confidence": 0.0}'
        )
        try:
            parsed, model_used = generate_structured_json(
                prompt,
                required_keys=["subject", "difficulty"],
            )
            subj = next(
                (s for s in subjects if s.name.lower() == str(parsed["subject"]).lower()),
                None,
            )
            ch = (
                next(
                    (c for c in subj.chapters if c.name.lower() == str(parsed.get("chapter", "")).lower()),
                    subj.chapters[0] if subj.chapters else None,
                )
                if subj
                else None
            )
            tp = (
                next(
                    (t for t in ch.topics if t.name.lower() == str(parsed.get("topic", "")).lower()),
                    ch.topics[0] if ch.topics else None,
                )
                if ch
                else None
            )
            cp = tp.concepts[0] if (tp and tp.concepts) else None
            if subj:
                diff = str(parsed.get("difficulty", "medium")).lower()
                if diff not in ("easy", "medium", "hard"):
                    diff = "medium"
                return {
                    "subject_id": subj.id,
                    "chapter_id": ch.id if ch else None,
                    "topic_id": tp.id if tp else None,
                    "concept_id": cp.id if cp else None,
                    "difficulty": diff,
                    "confidence": float(parsed.get("confidence", 0.8)),
                    "method": f"llm:{model_used}",
                }
        except (LLMUnavailableError, LLMSchemaError):
            pass

    return _keyword_classify(statement_md, subjects)
