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
