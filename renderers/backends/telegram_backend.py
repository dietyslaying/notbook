import html
from typing import List, Any
from ..core import IncrementalRenderer

class TelegramBackend(IncrementalRenderer):
    """
    Maps layout components to Telegram HTML and inline keyboards.
    """
    
    def _safe_escape(self, text: Any) -> str:
        if text is None:
            return ""
        return html.escape(str(text))
        
    async def render_incremental(self, component_stream):
        """
        Asynchronously consumes the layout component stream and yields 
        rendered Telegram HTML chunks when semantic boundaries are hit.
        """
        current_html_buffer = ""
        
        async for component in component_stream:
            c_type = getattr(component, "type", None)
            
            if c_type == "heading":
                icon = getattr(component, "icon", "")
                text = self._safe_escape(getattr(component, "text", ""))
                current_html_buffer += f"<b>{icon} {text}</b>\n\n"
                
            elif c_type == "paragraph":
                text = self._safe_escape(getattr(component, "text", ""))
                current_html_buffer += f"{text}\n\n"
                
            elif c_type == "checklist":
                items = getattr(component, "items", [])
                for item in items:
                    current_html_buffer += f"• {self._safe_escape(item)}\n"
                current_html_buffer += "\n"
                
            elif c_type == "divider":
                current_html_buffer += "──────────\n\n"
                
            # Yield accumulated HTML on natural boundaries (e.g. after a paragraph or checklist)
            if current_html_buffer.strip():
                yield current_html_buffer
                current_html_buffer = ""
                
        # Flush any remaining buffer
        if current_html_buffer.strip():
            yield current_html_buffer
