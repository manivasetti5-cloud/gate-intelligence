"""AI answer generation and structured 8-section GATE explanation solver."""

import re
from typing import Any

import sympy as sp

from app.services.llm_client import (
    LLMSchemaError,
    LLMUnavailableError,
    generate_structured_json,
    is_llm_configured,
)


def try_sympy_numeric_solve(statement_md: str) -> dict[str, Any] | None:
    """
    Attempt deterministic SymPy solving for simple explicit algebraic/arithmetic expressions
    embedded in NAT questions (used both as solver aid and independent verification).
    """
    # Look for explicit "evaluate <expr>" or "value of <expr>" patterns
    match = re.search(
        r"(?:value\s+of|evaluate|compute|find)\s+([0-9x\+\-\*/\^\(\)\.\s=]+)",
        statement_md,
        re.IGNORECASE,
    )
    if not match:
        return None
    expr_str = match.group(1).strip().rstrip("?.")
    if not any(ch.isdigit() for ch in expr_str):
        return None
    try:
        expr_str = expr_str.replace("^", "**")
        if "=" in expr_str:
            lhs, rhs = expr_str.split("=", 1)
            x = sp.Symbol("x")
            sol = sp.solve(sp.sympify(lhs) - sp.sympify(rhs), x)
            if sol and sol[0].is_real:
                val = float(sol[0].evalf())
                return {"value": round(val, 4), "tool": "sympy_equation_solver"}
        else:
            val = float(sp.sympify(expr_str).evalf())
            return {"value": round(val, 4), "tool": "sympy_expr_eval"}
    except Exception:
        return None


def solve_question_with_ai(
    *,
    statement_md: str,
    question_type: str,
    options: list[dict] | None = None,
    marks: int = 1,
) -> dict[str, Any]:
    """
    Solve an extracted GATE question and generate a complete 8-section explanation.
    Returns status='ai_solved' or 'unsolved_needs_review' when LLM is not configured.
    """
    qtype = question_type.upper()

    if is_llm_configured():
        opts_text = "\n".join(f"({o['label']}) {o['text']}" for o in (options or []))
        prompt = (
            "Solve the following GATE examination question accurately.\n"
            f"Question Type: {qtype} | Marks: {marks}\n"
            f"Statement:\n{statement_md}\n"
            + (f"Options:\n{opts_text}\n" if opts_text else "")
            + "\nReturn valid JSON with exact keys:\n"
            "{\n"
            '  "correct_answer": <for MCQ: "A"|"B"|"C"|"D"; for MSQ: ["A","C"]; for NAT: 12.5>,\n'
            '  "nat_min": <number or null>,\n'
            '  "nat_max": <number or null>,\n'
            '  "confidence": <0.0 to 1.0>,\n'
            '  "verification_expression": <optional Python/SymPy arithmetic expression verifying numerical result, or "">,\n'
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
                required_keys=["correct_answer", "explanation"],
            )
            ans = parsed["correct_answer"]
            if qtype == "MCQ":
                correct_json = {"option": str(ans).strip().upper()[:1]}
            elif qtype == "MSQ":
                opts_list = ans if isinstance(ans, list) else [str(ans)]
                correct_json = {"options": sorted({str(x).strip().upper()[:1] for x in opts_list})}
            else:
                num = float(ans)
                correct_json = {"value": num}

            return {
                "solved": True,
                "model_used": model_used,
                "correct_answer_json": correct_json,
                "nat_min": parsed.get("nat_min"),
                "nat_max": parsed.get("nat_max"),
                "confidence": float(parsed.get("confidence", 0.75)),
                "verification_expression": parsed.get("verification_expression", ""),
                "explanation_json": parsed.get("explanation", {}),
            }
        except (LLMUnavailableError, LLMSchemaError, ValueError, TypeError):
            pass

    # If LLM unavailable, try deterministic SymPy for NAT expressions
    if qtype == "NAT":
        sym = try_sympy_numeric_solve(statement_md)
        if sym:
            val = sym["value"]
            return {
                "solved": True,
                "model_used": sym["tool"],
                "correct_answer_json": {"value": val},
                "nat_min": round(val - 0.01, 4),
                "nat_max": round(val + 0.01, 4),
                "confidence": 0.9,
                "verification_expression": "",
                "explanation_json": {
                    "concept_explanation": "Solved deterministically via SymPy symbolic evaluation.",
                    "step_by_step": f"Symbolic/numeric evaluation yielded {val}.",
                    "formula_used": "",
                    "shortcut_method": "",
                    "alternative_method": "",
                    "common_mistakes": "",
                    "option_analysis": "Numerical Answer Type question.",
                    "gate_tip": "Double-check rounding precision required by the question.",
                },
            }

    return {
        "solved": False,
        "model_used": "none",
        "correct_answer_json": {},
        "nat_min": None,
        "nat_max": None,
        "confidence": 0.0,
        "verification_expression": "",
        "explanation_json": {},
    }
