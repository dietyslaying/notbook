"""Map NDM dict → ordered UI pages (overview, sections, citations, source)."""

from __future__ import annotations

from interfaces import UIComponent


class ComponentPolicy:
    @staticmethod
    def map_to_ui_components(ndm_data: dict) -> list[UIComponent]:
        if "error" in ndm_data:
            return [UIComponent(component_type="error", data=ndm_data["error"])]
        components: list[UIComponent] = [
            UIComponent(component_type="title", data=ndm_data.get("title", "Topic")),
            UIComponent(component_type="summary", data=ndm_data.get("summary", "")),
            UIComponent(component_type="fact_list", data=ndm_data.get("core_facts") or []),
            UIComponent(component_type="source", data=ndm_data.get("source_citation", "")),
        ]
        for sec in ndm_data.get("detail_sections") or []:
            if isinstance(sec, dict):
                components.append(
                    UIComponent(
                        component_type="section",
                        data={
                            "heading": sec.get("heading") or "Details",
                            "body": sec.get("body") or "",
                        },
                    )
                )
        return components

    @staticmethod
    def build_pages(
        ndm_data: dict,
        disclaimer: str = "",
        *,
        emergency_banner: str = "",
        mode_label: str = "",
    ) -> list[dict]:
        if "error" in ndm_data:
            return [{"kind": "error", "data": ndm_data["error"]}]

        pages: list[dict] = [
            {
                "kind": "overview",
                "title": ndm_data.get("title", "Topic"),
                "summary": ndm_data.get("summary", ""),
                "facts": ndm_data.get("core_facts") or [],
                "disclaimer": disclaimer,
                "emergency_banner": emergency_banner,
                "mode_label": mode_label,
            }
        ]

        for sec in ndm_data.get("detail_sections") or []:
            if not isinstance(sec, dict):
                continue
            body = (sec.get("body") or "").strip()
            heading = (sec.get("heading") or "Details").strip()
            if not body:
                continue
            pages.append({"kind": "section", "heading": heading, "body": body})

        citations = ndm_data.get("citations") or []
        if citations:
            pages.append({"kind": "citations", "citations": citations})

        pages.append(
            {
                "kind": "source",
                "source": ndm_data.get("source_citation") or "Textbook excerpt",
                "disclaimer": disclaimer,
            }
        )
        return pages
