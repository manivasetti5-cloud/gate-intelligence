"""GATE question segmentation from extracted PDF page text and diagrams."""

import re
from typing import Any

from app.services.pdf_extractor import ExtractedPage

QUESTION_HEADER_RE = re.compile(
    r"(?:^|\n)\s*(?:Q\.?\s*(?:No\.?)?\s*|Question\s+)(\d{1,3})(?:\s*[\.\):\-]\s*|\s+)",
    re.IGNORECASE,
)
OPTION_RE = re.compile(
    r"(?:^|\n)\s*\(?([A-D])\)[\.\s]+(.*?)(?=(?:\n\s*\(?[A-D]\)[\.\s]+)|\Z)",
    re.DOTALL,
)
MARKS_RE = re.compile(r"\[?\s*([12])\s*Marks?\s*\]?", re.IGNORECASE)


def _infer_question_type(raw_block: str, options: list[dict]) -> str:
    upper = raw_block.upper()
    if "[MSQ]" in upper or "MULTIPLE SELECT" in upper:
        return "MSQ"
    if "[NAT]" in upper or "NUMERICAL ANSWER" in upper or not options:
        return "NAT"
    return "MCQ"


def segment_pages_into_questions(pages: list[ExtractedPage]) -> list[dict[str, Any]]:
    """
    Segment extracted page text into structured question blocks while preserving page numbers
    and associating any page diagrams/figures.
    """
    results: list[dict[str, Any]] = []

    for page in pages:
        text = page.text or ""
        matches = list(QUESTION_HEADER_RE.finditer(text))
        if not matches:
            continue

        for idx, match in enumerate(matches):
            q_num = match.group(1)
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            block = text[start:end].strip()
            if len(block) < 12:
                continue

            marks_match = MARKS_RE.search(block)
            marks = int(marks_match.group(1)) if marks_match else 1

            # Split statement from options if options (A)...(D) exist
            opt_matches = list(OPTION_RE.finditer(block))
            options: list[dict[str, Any]] = []
            statement = block
            if len(opt_matches) >= 2:
                statement = block[: opt_matches[0].start()].strip()
                for om in opt_matches:
                    opt_label = om.group(1).upper()
                    opt_text = re.sub(r"\s+", " ", om.group(2)).strip()
                    options.append({"label": opt_label, "text": opt_text})

            statement_clean = MARKS_RE.sub("", statement).strip()
            qtype = _infer_question_type(block, options)

            results.append(
                {
                    "page_number": page.page_number,
                    "raw_q_number": q_num,
                    "raw_text": block,
                    "statement_md": statement_clean or block,
                    "options": options,
                    "marks": marks,
                    "question_type": qtype,
                    "image_paths": list(page.image_paths),
                    "confidence_score": 0.85 if (options or qtype == "NAT") else 0.55,
                }
            )

    return results
