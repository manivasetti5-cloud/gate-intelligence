"""Independent answer verification stage (SymPy symbolic/numeric + second-pass AI verifier)."""

import os
from typing import Any

import sympy as sp

from app.services.answer_solver import try_sympy_numeric_solve
from app.services.llm_client import (
    LLMSchemaError,
    LLMUnavailableError,
    generate_structured_json,
    is_llm_configured,
)


def _eval_sympy_expression(expr: str) -> float | None:
    """Safely evaluate a pure mathematical SymPy expression without arbitrary Python exec."""
    if not expr or len(expr) > 200:
        return None
    try:
        parsed = sp.sympify(expr.replace("^", "**"))
        if parsed.free_symbols:
            return None
        return float(parsed.evalf())
    except Exception:
        return None


def verify_proposed_answer(
    *,
    statement_md: str,
    question_type: str,
    proposed_answer_json: dict,
    options: list[dict] | None = None,
    verification_expression: str = "",
    primary_confidence: float = 0.0,
) -> dict[str, Any]:
    """
    Independently verify a proposed answer using SymPy and/or a second LLM pass.
    Returns verification_status in:
      - 'verified'
      - 'ai_solved_awaiting_verification'
      - 'needs_manual_review'
    """
    qtype = question_type.upper()
    if not proposed_answer_json:
        return {
            "verification_status": "needs_manual_review",
            "is_match": False,
            "verifier_type": "system_check",
            "model_or_tool": "none",
            "confidence_score": 0.0,
            "notes": "No proposed answer was generated; requires administrator review.",
        }

    # 1. SymPy numeric/symbolic independent validation for NAT
    if qtype == "NAT" and "value" in proposed_answer_json:
        target_val = float(proposed_answer_json["value"])
        if verification_expression:
            sym_val = _eval_sympy_expression(verification_expression)
            if sym_val is not None:
                match = abs(sym_val - target_val) <= max(1e-3, abs(target_val) * 1e-3)
                return {
                    "verification_status": "verified" if match else "needs_manual_review",
                    "is_match": match,
                    "verifier_type": "sympy_numeric",
                    "model_or_tool": "sympy",
                    "confidence_score": 0.98 if match else 0.1,
                    "notes": f"SymPy evaluated '{verification_expression}' = {sym_val} vs proposed {target_val}.",
                }
        direct_sym = try_sympy_numeric_solve(statement_md)
        if direct_sym:
            sym_val = float(direct_sym["value"])
            match = abs(sym_val - target_val) <= max(1e-2, abs(target_val) * 1e-2)
            return {
                "verification_status": "verified" if match else "needs_manual_review",
                "is_match": match,
                "verifier_type": "sympy_numeric",
                "model_or_tool": direct_sym["tool"],
                "confidence_score": 0.95 if match else 0.15,
                "notes": f"Independent SymPy check: {sym_val} vs proposed {target_val}.",
            }

    # 2. Second-pass independent LLM verifier
    if is_llm_configured():
        verifier_model = os.getenv("GEMINI_VERIFIER_MODEL", "gemini-2.5-pro")
        opts_text = "\n".join(f"({o['label']}) {o['text']}" for o in (options or []))
        prompt = (
            "Independently verify the answer to this GATE question from scratch.\n"
            f"Question Type: {qtype}\nStatement:\n{statement_md}\n"
            + (f"Options:\n{opts_text}\n" if opts_text else "")
            + '\nReturn JSON: {"independent_answer": ..., "confidence": 0.0}'
        )
        try:
            parsed, model_used = generate_structured_json(
                prompt,
                model_name=verifier_model,
                required_keys=["independent_answer"],
            )
            ind = parsed["independent_answer"]
            match = False
            if qtype == "MCQ":
                match = str(ind).strip().upper()[:1] == str(proposed_answer_json.get("option", "")).upper()
            elif qtype == "MSQ":
                ind_set = {str(x).strip().upper()[:1] for x in (ind if isinstance(ind, list) else [ind])}
                prop_set = {str(x).upper() for x in proposed_answer_json.get("options", [])}
                match = ind_set == prop_set and len(prop_set) > 0
            elif qtype == "NAT":
                ind_val = float(ind)
                prop_val = float(proposed_answer_json["value"])
                match = abs(ind_val - prop_val) <= max(0.02, abs(prop_val) * 0.01)

            conf = float(parsed.get("confidence", 0.8))
            if match and conf >= 0.75 and primary_confidence >= 0.7:
                status = "verified"
            elif match:
                status = "ai_solved_awaiting_verification"
            else:
                status = "needs_manual_review"

            return {
                "verification_status": status,
                "is_match": match,
                "verifier_type": "second_llm",
                "model_or_tool": model_used,
                "confidence_score": conf,
                "notes": f"Independent second solver returned {ind}.",
            }
        except (LLMUnavailableError, LLMSchemaError, ValueError, TypeError):
            pass

    return {
        "verification_status": "ai_solved_awaiting_verification",
        "is_match": False,
        "verifier_type": "pending_verification",
        "model_or_tool": "none",
        "confidence_score": primary_confidence,
        "notes": "Primary answer generated; awaiting independent verification before publishing.",
    }
