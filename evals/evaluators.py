"""Evaluators. Each returns a dict with key, score, and comment so the reason
for a score is visible in LangSmith, not just the number.

Two kinds:
- code evaluators, deterministic and free, run on every example
- an LLM judge, optional, only built if OPENAI_API_KEY is set
"""
from __future__ import annotations

import os
import re
import unicodedata


def _norm(text: str) -> str:
    """Fold unicode variants and whitespace so 'SKU‑1042' matches 'SKU-1042'."""
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = re.sub(r"[‐‑‒–—−]", "-", text)  # every dash variant -> "-"
    text = text.replace(" ", " ").replace("\xa0", " ")
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)  # 1,250.00 -> 1250.00
    return re.sub(r"\s+", " ", text).strip().lower()


def response_present(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    ok = bool(_norm(outputs.get("answer")))
    return {"key": "response_present", "score": float(ok), "comment": "" if ok else "empty answer"}


def keyword_coverage(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Share of expected keywords found in the answer. Lenient on formatting."""
    expected = reference_outputs.get("expected_keywords") or []
    if not expected:
        return {"key": "keyword_coverage", "score": None, "comment": "no expected_keywords on example"}
    answer = _norm(outputs.get("answer"))
    missing = [k for k in expected if _norm(k) not in answer]
    score = (len(expected) - len(missing)) / len(expected)
    comment = f"matched {len(expected) - len(missing)} of {len(expected)}"
    if missing:
        comment += f", missing: {', '.join(missing)}"
    return {"key": "keyword_coverage", "score": round(score, 3), "comment": comment}


def build_evaluators() -> list:
    evaluators = [response_present, keyword_coverage]
    if os.environ.get("OPENAI_API_KEY"):
        from openevals.llm import create_llm_as_judge
        from openevals.prompts import CORRECTNESS_PROMPT

        judge = create_llm_as_judge(
            prompt=CORRECTNESS_PROMPT,
            feedback_key="correctness",
            model=os.environ.get("JUDGE_MODEL", "openai:gpt-4o-mini"),
        )

        def correctness(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
            return judge(
                inputs=inputs,
                outputs=outputs.get("answer"),
                reference_outputs=reference_outputs.get("reference_answer"),
            )

        evaluators.append(correctness)
    return evaluators
