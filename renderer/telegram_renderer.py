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
                    elif comp.component_type == "checklist":
                        items = comp.payload.get("items", [])
                        for item in items:
                            text = html.escape(item)
                            html_lines.append(f"• {text}")
                        html_lines.append("")
                    elif comp.component_type == "comparison":
                        # Render comparison as a clean text list (tables not supported on TG)
                        topic_a = html.escape(comp.payload.get("topic_a", "Topic A"))
                        topic_b = html.escape(comp.payload.get("topic_b", "Topic B"))
                        html_lines.append(f"⚖️ <b>COMPARISON: {topic_a} vs {topic_b}</b>")
                        
                        aspects = comp.payload.get("aspects", [])
                        for aspect_data in aspects:
                            aspect_name = html.escape(aspect_data.get("aspect", ""))
                            a_val = html.escape(aspect_data.get("topic_a_value", ""))
                            b_val = html.escape(aspect_data.get("topic_b_value", ""))
                            html_lines.append(f"• <b>{aspect_name}</b>: {a_val} | {b_val}")
                        html_lines.append("")
                    elif comp.component_type == "reference":
                        source = html.escape(comp.payload.get("source", "Reference"))
                        pages = html.escape(str(comp.payload.get("pages", "")))
                        pages_str = f" (p. {pages})" if pages else ""
                        html_lines.append(f"📚 <i>Source: {source}{pages_str}</i>\n")
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
