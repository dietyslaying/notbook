import html
import logging
from interfaces import IRenderer, Document, TelegramScreen
from renderer.keyboard_builder import build_keyboard

logger = logging.getLogger(__name__)

class TelegramRenderer(IRenderer):
    def render(self, document: Document) -> TelegramScreen:
        messages = []
        
        # Add topic header as first message (or combined with first component)
        topic = html.escape(document.topic) if document.topic else ""
        header = f"<b>{topic}</b>\n\n" if topic else ""
        
        is_first = True
        
        # Render sections
        for section in document.sections:
            for comp in section.components:
                try:
                    comp_html = ""
                    if is_first and header:
                        comp_html += header
                        is_first = False
                        
                    if comp.component_type == "paragraph":
                        text = html.escape(comp.payload.get("text", ""))
                        comp_html += f"{text}"
                    elif comp.component_type == "explanation":
                        topic = html.escape(comp.payload.get("topic", ""))
                        content = html.escape(comp.payload.get("content", ""))
                        comp_html += f"<b>{topic}</b>\n\n{content}"
                    elif comp.component_type == "checklist":
                        heading = html.escape(comp.payload.get("heading", ""))
                        if heading:
                            comp_html += f"<b>{heading}</b>\n\n"
                        items = comp.payload.get("items", [])
                        for item in items:
                            text = html.escape(item)
                            comp_html += f"• {text}\n\n"
                        comp_html = comp_html.strip()
                    elif comp.component_type == "treatment":
                        condition = html.escape(comp.payload.get("condition", ""))
                        comp_html += f"💊 <b>Treatment: {condition}</b>\n\n"
                        treatments = comp.payload.get("treatments", [])
                        for trt in treatments:
                            comp_html += f"• {html.escape(trt)}\n\n"
                        notes = comp.payload.get("notes")
                        if notes:
                            comp_html += f"<blockquote><i>Note: {html.escape(notes)}</i></blockquote>"
                        comp_html = comp_html.strip()
                    elif comp.component_type == "drug_card":
                        drug_name = html.escape(comp.payload.get("drug_name", ""))
                        drug_class = html.escape(comp.payload.get("drug_class", ""))
                        class_str = f" ({drug_class})" if drug_class else ""
                        comp_html += f"💊 <b>{drug_name}</b>{class_str}\n\n"
                        
                        mech = comp.payload.get("mechanism")
                        if mech:
                            comp_html += f"<b>MECHANISM</b>\n• {html.escape(mech)}\n\n"
                        
                        for section_title, key in [("INDICATIONS", "indications"), ("CONTRAINDICATIONS", "contraindications"), ("SIDE EFFECTS", "side_effects")]:
                            items = comp.payload.get(key, [])
                            if items:
                                comp_html += f"<b>{section_title}</b>\n"
                                for item in items:
                                    comp_html += f"• {html.escape(item)}\n\n"
                        comp_html = comp_html.strip()
                    elif comp.component_type == "comparison":
                        topic_a = html.escape(comp.payload.get("topic_a", "Topic A"))
                        topic_b = html.escape(comp.payload.get("topic_b", "Topic B"))
                        comp_html += f"⚖️ <b>COMPARISON: {topic_a} vs {topic_b}</b>\n\n"
                        aspects = comp.payload.get("aspects", [])
                        for aspect_data in aspects:
                            aspect_name = html.escape(aspect_data.get("aspect", ""))
                            a_val = html.escape(aspect_data.get("a", ""))
                            b_val = html.escape(aspect_data.get("b", ""))
                            comp_html += f"• <b>{aspect_name}</b>:\n  {a_val}\n  <b>VS</b>\n  {b_val}\n\n"
                        comp_html = comp_html.strip()
                    elif comp.component_type == "timeline":
                        comp_html += "🕐 <b>Timeline</b>\n\n"
                        events = comp.payload.get("events", [])
                        for ev in events:
                            t = html.escape(ev.get("time", ""))
                            e = html.escape(ev.get("event", ""))
                            comp_html += f"<b>{t}</b> — {e}\n\n"
                        comp_html = comp_html.strip()
                    elif comp.component_type == "formula":
                        name = html.escape(comp.payload.get("name", ""))
                        expr = html.escape(comp.payload.get("expression", ""))
                        comp_html += f"<b>{name}</b>\n\n<code>{expr}</code>\n\n"
                        vars_list = comp.payload.get("variables", [])
                        if vars_list:
                            comp_html += "<b>Where:</b>\n"
                            for var in vars_list:
                                v_name = html.escape(var.get("name", ""))
                                v_meaning = html.escape(var.get("meaning", ""))
                                comp_html += f"• {v_name} = {v_meaning}\n"
                        comp_html = comp_html.strip()
                    elif comp.component_type == "guideline":
                        org = html.escape(comp.payload.get("organization", ""))
                        comp_html += f"📜 <b>{org} Guidelines</b>\n\n<blockquote>"
                        recs = comp.payload.get("recommendations", [])
                        for rec in recs:
                            comp_html += f"• {html.escape(rec)}\n\n"
                        comp_html = comp_html.strip() + "</blockquote>"
                    elif comp.component_type == "clinical_case":
                        comp_html += "🩺 <b>Clinical Case</b>\n\n<blockquote>"
                        pres = html.escape(comp.payload.get("patient_presentation", ""))
                        comp_html += f"<i>{pres}</i>\n\n"
                        findings = comp.payload.get("key_findings", [])
                        if findings:
                            comp_html += "<b>Key Findings</b>\n"
                            for f in findings:
                                comp_html += f"• {html.escape(f)}\n"
                        diagnosis = comp.payload.get("diagnosis")
                        if diagnosis:
                            comp_html += f"\n<b>Diagnosis:</b> {html.escape(diagnosis)}"
                        comp_html += "</blockquote>"
                    elif comp.component_type == "reference":
                        source = html.escape(comp.payload.get("source", "Reference"))
                        pages = html.escape(str(comp.payload.get("page", "")))
                        pages_str = f" (p. {pages})" if pages and pages != "None" else ""
                        comp_html += f"📚 <i>Source: {source}{pages_str}</i>"
                    elif comp.component_type == "definition":
                        term = html.escape(comp.payload.get("term", ""))
                        definition = html.escape(comp.payload.get("definition", ""))
                        comp_html += f"<blockquote><b>{term}</b>\n\n{definition}</blockquote>"
                    elif comp.component_type == "concept":
                        name = html.escape(comp.payload.get("name", ""))
                        comp_html += f"📌 <b>{name}</b>\n\n"
                        details = comp.payload.get("details", [])
                        for d in details:
                            comp_html += f"• {html.escape(d)}\n\n"
                        comp_html = comp_html.strip()
                    else:
                        logger.warning(f"Unknown component type: {comp.component_type}")
                        
                    if comp_html.strip():
                        messages.append(comp_html.strip())
                except Exception as e:
                    logger.error(f"Failed to render component {comp.component_type}: {e}")
                    
        # If there are no components but there is a header
        if not messages and header:
            messages.append(header.strip())
            
        # Build keyboard
        keyboard = None
        if document.ia_schema:
            keyboard = build_keyboard(document.ia_schema)
            
        return TelegramScreen(messages=messages, keyboard=keyboard)
