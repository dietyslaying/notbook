"""Case work-up workspace: patient vignettes → locked 16-section framework.

Triggered before intent classification when the query looks like a patient
case (see case_framework.is_case_prompt). Renders the full case HTML itself
and hands it to the pipeline via ndm["case_html"].
"""

from __future__ import annotations

import logging

from interfaces import IntentType
from services.gemini_service import gemini_service
from workspaces.base import BaseWorkspace

import case_framework as cf

logger = logging.getLogger(__name__)


class CaseWorkspace(BaseWorkspace):
    intent = IntentType.UNKNOWN  # bypasses intent classification

    @staticmethod
    def matches(query: str) -> bool:
        return cf.is_case_prompt(query)

    async def process(
        self,
        query: str,
        study_mode: str = "standard",
        namespaces: list[str] | None = None,
    ) -> dict:
        q = (query or "").strip()
        if not q:
            return {"error": "Empty question."}

        context, source_hint, citations = await gemini_service.retrieve(
            q, namespaces=namespaces
        )
        if not context:
            return {
                "error": (
                    "I couldn't find excerpts covering this case in the sources. "
                    "Try different wording or pick a different source from the menu."
                )
            }

        archetype = cf.detect_archetype(q)
        prompt = cf.build_prompt(
            query=q,
            archetype=archetype,
            study_mode=study_mode,
            context=context,
            namespaces=namespaces,
        )
        try:
            raw = await gemini_service.generate_json(prompt)
        except Exception as e:
            logger.exception("case generation failed")
            return {"error": f"Generation failed. Please try again. ({type(e).__name__})"}

        data = cf.validate_case_json(raw)
        if "error" in data:
            # One repair retry: the model may have wrapped JSON in prose/fences.
            logger.warning("case JSON parse failed, retrying with repair hint")
            try:
                raw = await gemini_service.generate_json(
                    prompt
                    + "\n\nIMPORTANT: Your previous response was not parseable JSON. "
                    "Return ONLY the JSON object itself — no markdown fences, no commentary."
                )
                data = cf.validate_case_json(raw)
            except Exception as e:
                logger.exception("case repair retry failed")
                return {"error": f"Generation failed. Please try again. ({type(e).__name__})"}
        if "error" in data:
            return data

        scope = cf.scope_label(namespaces)
        html = cf.render_case(data, citations, scope_label=scope, archetype=archetype)
        return {
            "title": cf.title_for(q),
            "summary": cf.one_line(data),
            "core_facts": [],
            "detail_sections": [],
            "case_html": html,
            "source_citation": source_hint or "Excerpt",
            "citations": citations,
            "study_mode": study_mode,
            "route": {"strategy": "case", "reason": "patient vignette detected", "selected": namespaces or [], "total": 0},
        }
