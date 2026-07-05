import html
import logging
from interfaces import IRenderer, Document, TelegramScreen
from renderer.keyboard_builder import build_keyboard

logger = logging.getLogger(__name__)

class TelegramRenderer(IRenderer):
    def render(self, document: Document) -> TelegramScreen:
        html_lines = []
        
        # Add topic header
        topic = html.escape(document.topic) if document.topic else ""
        if topic:
            html_lines.append(f"<b>{topic}</b>\n")
            
        # Render sections
        for section in document.sections:
            for comp in section.components:
                try:
                    if comp.component_type == "paragraph":
                        text = html.escape(comp.payload.get("text", ""))
                        html_lines.append(f"{text}\n")
                    elif comp.component_type == "explanation":
                        topic = html.escape(comp.payload.get("topic", ""))
                        content = html.escape(comp.payload.get("content", ""))
                        html_lines.append(f"<b>{topic}</b>\n{content}\n")
                    elif comp.component_type == "checklist":
                        heading = html.escape(comp.payload.get("heading", ""))
                        if heading:
                            html_lines.append(f"<b>{heading}</b>")
                        items = comp.payload.get("items", [])
                        for item in items:
                            text = html.escape(item)
                            html_lines.append(f"• {text}")
                        html_lines.append("")
                    elif comp.component_type == "treatment":
                        condition = html.escape(comp.payload.get("condition", ""))
                        html_lines.append(f"💊 <b>Treatment: {condition}</b>")
                        treatments = comp.payload.get("treatments", [])
                        for trt in treatments:
                            html_lines.append(f"• {html.escape(trt)}")
                        notes = comp.payload.get("notes")
                        if notes:
                            html_lines.append(f"<i>Note: {html.escape(notes)}</i>")
                        html_lines.append("")
                    elif comp.component_type == "drug_card":
                        drug_name = html.escape(comp.payload.get("drug_name", ""))
                        drug_class = html.escape(comp.payload.get("drug_class", ""))
                        class_str = f" ({drug_class})" if drug_class else ""
                        html_lines.append(f"💊 <b>{drug_name}</b>{class_str}")
                        
                        mech = comp.payload.get("mechanism")
                        if mech:
                            html_lines.append(f"<b>MECHANISM</b>\n• {html.escape(mech)}")
                        
                        for section_title, key in [("INDICATIONS", "indications"), ("CONTRAINDICATIONS", "contraindications"), ("SIDE EFFECTS", "side_effects")]:
                            items = comp.payload.get(key, [])
                            if items:
                                html_lines.append(f"<b>{section_title}</b>")
                                for item in items:
                                    html_lines.append(f"• {html.escape(item)}")
                        html_lines.append("")
                    elif comp.component_type == "comparison":
                        topic_a = html.escape(comp.payload.get("topic_a", "Topic A"))
                        topic_b = html.escape(comp.payload.get("topic_b", "Topic B"))
                        html_lines.append(f"⚖️ <b>COMPARISON: {topic_a} vs {topic_b}</b>")
                        aspects = comp.payload.get("aspects", [])
                        for aspect_data in aspects:
                            aspect_name = html.escape(aspect_data.get("aspect", ""))
                            a_val = html.escape(aspect_data.get("a", ""))
                            b_val = html.escape(aspect_data.get("b", ""))
                            html_lines.append(f"• <b>{aspect_name}</b>: {a_val} | {b_val}")
                        html_lines.append("")
                    elif comp.component_type == "timeline":
                        html_lines.append("🕐 <b>Timeline</b>")
                        events = comp.payload.get("events", [])
                        for ev in events:
                            t = html.escape(ev.get("time", ""))
                            e = html.escape(ev.get("event", ""))
                            html_lines.append(f"{t} — {e}")
                        html_lines.append("")
                    elif comp.component_type == "formula":
                        name = html.escape(comp.payload.get("name", ""))
                        expr = html.escape(comp.payload.get("expression", ""))
                        html_lines.append(f"<b>{name}</b>\n<code>{expr}</code>")
                        vars_list = comp.payload.get("variables", [])
                        if vars_list:
                            html_lines.append("Where:")
                            for var in vars_list:
                                v_name = html.escape(var.get("name", ""))
                                v_meaning = html.escape(var.get("meaning", ""))
                                html_lines.append(f"• {v_name} = {v_meaning}")
                        html_lines.append("")
                    elif comp.component_type == "guideline":
                        org = html.escape(comp.payload.get("organization", ""))
                        html_lines.append(f"📜 <b>{org} Guidelines</b>")
                        recs = comp.payload.get("recommendations", [])
                        for rec in recs:
                            html_lines.append(f"• {html.escape(rec)}")
                        html_lines.append("")
                    elif comp.component_type == "clinical_case":
                        html_lines.append("🩺 <b>Clinical Case</b>")
                        pres = html.escape(comp.payload.get("patient_presentation", ""))
                        html_lines.append(f"{pres}\n")
                        findings = comp.payload.get("key_findings", [])
                        if findings:
                            html_lines.append("<b>Key Findings</b>")
                            for f in findings:
                                html_lines.append(f"• {html.escape(f)}")
                        diagnosis = comp.payload.get("diagnosis")
                        if diagnosis:
                            html_lines.append(f"\n<b>Diagnosis:</b> {html.escape(diagnosis)}")
                        html_lines.append("")
                    elif comp.component_type == "reference":
                        source = html.escape(comp.payload.get("source", "Reference"))
                        pages = html.escape(str(comp.payload.get("page", "")))
                        pages_str = f" (p. {pages})" if pages and pages != "None" else ""
                        html_lines.append(f"📚 <i>Source: {source}{pages_str}</i>\n")
                    elif comp.component_type == "definition":
                        term = html.escape(comp.payload.get("term", ""))
                        definition = html.escape(comp.payload.get("definition", ""))
                        html_lines.append(f"<b>{term}</b>\n{definition}\n")
                    elif comp.component_type == "concept":
                        name = html.escape(comp.payload.get("name", ""))
                        html_lines.append(f"📌 <b>{name}</b>")
                        details = comp.payload.get("details", [])
                        for d in details:
                            html_lines.append(f"• {html.escape(d)}")
                        html_lines.append("")
                    else:
                        logger.warning(f"Unknown component type: {comp.component_type}")
                except Exception as e:
                    logger.error(f"Failed to render component {comp.component_type}: {e}")
                    
        rendered_html = "\n".join(html_lines).strip()
        
        # Build keyboard
        keyboard = None
        if document.ia_schema:
            keyboard = build_keyboard(document.ia_schema)
            
        return TelegramScreen(html=rendered_html, keyboard=keyboard)
