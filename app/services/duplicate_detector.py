"""Duplicate question detection using normalized hashing, TF-IDF cosine similarity, and perceptual image hashing."""

from pathlib import Path
from typing import Any

from PIL import Image
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.models.question import Question
from app.services.question_service import compute_normalized_hash


def compute_image_dhash(image_path: str | Path, hash_size: int = 8) -> str | None:
    """Compute a 64-bit difference hash (dHash) for an extracted diagram image."""
    try:
        with Image.open(image_path) as img:
            gray = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
            pixels = list(gray.getdata())
            diff_bits = []
            for row in range(hash_size):
                row_start = row * (hash_size + 1)
                for col in range(hash_size):
                    diff_bits.append(1 if pixels[row_start + col] > pixels[row_start + col + 1] else 0)
            hex_val = 0
            for bit in diff_bits:
                hex_val = (hex_val << 1) | bit
            return f"{hex_val:016x}"
    except Exception:
        return None


def find_duplicate_question(
    *,
    branch_id: int,
    statement_md: str,
    similarity_threshold: float = 0.88,
) -> dict[str, Any]:
    """
    Check if a candidate question duplicates an existing question in the branch.
    Returns {"is_duplicate": bool, "matched_question_id": int | None, "similarity": float, "method": str}.
    """
    norm_hash = compute_normalized_hash(statement_md)
    exact = Question.query.filter_by(branch_id=branch_id, normalized_hash=norm_hash).first()
    if exact:
        return {
            "is_duplicate": True,
            "matched_question_id": exact.id,
            "similarity": 1.0,
            "method": "exact_normalized_hash",
        }

    existing = Question.query.filter_by(branch_id=branch_id).with_entities(
        Question.id, Question.statement_md
    ).all()
    if not existing:
        return {"is_duplicate": False, "matched_question_id": None, "similarity": 0.0, "method": "none"}

    corpus = [statement_md] + [row.statement_md for row in existing]
    try:
        vec = TfidfVectorizer(stop_words="english").fit_transform(corpus)
        sims = cosine_similarity(vec[0:1], vec[1:]).flatten()
        best_idx = int(sims.argmax())
        best_sim = float(sims[best_idx])
        if best_sim >= similarity_threshold:
            return {
                "is_duplicate": True,
                "matched_question_id": existing[best_idx].id,
                "similarity": round(best_sim, 3),
                "method": "tfidf_cosine",
            }
        return {
            "is_duplicate": False,
            "matched_question_id": None,
            "similarity": round(best_sim, 3),
            "method": "tfidf_cosine",
        }
    except Exception:
        return {"is_duplicate": False, "matched_question_id": None, "similarity": 0.0, "method": "none"}
