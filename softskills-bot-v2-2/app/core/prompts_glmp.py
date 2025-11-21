# app/core/prompts_glmp.py
from __future__ import annotations
from typing import Dict

SYSTEM_PROMPT = """You are a concise, fair, **skills** coach.
Use ONLY the structured metrics I'll give you (scores 0–10 with labels).
Don't infer persona/role/traits. No assumptions, no hallucinations.
Be specific and actionable. Greek output.
Return short bullets, within ~120 words total."""

USER_TEMPLATE = """SKILL: {skill_name}

DIMENSIONS:
{dims}

ATTRIBUTES:
{attrs}

Write:
- 2 strengths (ΚΡΑΤΑ)
- 2 improvements (ΑΛΛΑΞΕ)
- 1 next action (ΕΝΕΡΓΕΙΑ)
- 1 quick drill (ΑΣΚΗΣΗ)
Keep it concrete and aligned with the metrics.
"""

def _lines_from_section(sec: Dict[str, Dict[str, object]]) -> str:
    if not isinstance(sec, dict):
        return "-"
    lines = []
    for k, v in sec.items():
        score = v.get("score")
        label = v.get("label")
        lines.append(f"- {k}: {score}/10 ({label})")
    return "\n".join(lines) or "-"

def build_user_prompt(skill_name: str, sections: dict) -> str:
    dims = _lines_from_section(sections.get("dimensions", {}))
    attrs = _lines_from_section(sections.get("attributes", {}))
    return USER_TEMPLATE.format(skill_name=skill_name, dims=dims, attrs=attrs)

def default_system_prompt() -> str:
    return SYSTEM_PROMPT
