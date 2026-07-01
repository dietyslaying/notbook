import html
from typing import List, Any
from layout.components import RenderEvent
from engine.render_planner import StreamingPlan
from engine.interaction_engine import InteractionTree

class TelegramRichBackend:
    """
    Platform-specific backend for Telegram.
    Translates the agnostic RenderEvents and InteractionTree into Telegram HTML and Inline Keyboards.
    """
    
    def _safe_escape(self, text: Any) -> str:
        if text is None:
            return ""
        return html.escape(str(text))
        
    def render_streaming_plan(self, plan: StreamingPlan) -> str:
        """
        Executes a StreamingPlan synchronously for now (placeholder for real streaming).
        Returns the final HTML string.
        """
        current_html_buffer = ""
        
        for instruction in plan.instructions:
            if instruction.event == RenderEvent.ADD:
                data = instruction.data or {}
                
                # Render Section Header
                if "kind" in data:
                    kind = self._safe_escape(data.get("kind", ""))
                    current_html_buffer += f"<b>== {kind.upper()} ==</b>\n\n"
                    
                # Render Specific Components
                elif "type" in data:
                    c_type = data["type"]
                    payload = data.get("payload", {})
                    
                    if c_type == "title":
                        icon = payload.get("icon", "")
                        text = self._safe_escape(payload.get("text", ""))
                        current_html_buffer += f"<b>{icon} {text}</b>\n\n"
                        
                    elif c_type == "paragraph":
                        text = self._safe_escape(payload.get("text", ""))
                        current_html_buffer += f"{text}\n\n"
                        
                    elif c_type == "checklist":
                        items = payload.get("items", [])
                        for item in items:
                            current_html_buffer += f"• {self._safe_escape(item)}\n"
                        current_html_buffer += "\n"
                        
                    elif c_type == "table":
                        headers = payload.get("headers", [])
                        rows = payload.get("rows", [])
                        if headers:
                            current_html_buffer += f"<b>{self._safe_escape(headers[0])}</b>\n"
                        for row in rows:
                            if len(row) == 3:
                                current_html_buffer += f"• {self._safe_escape(row[0])}: {self._safe_escape(row[1])} vs {self._safe_escape(row[2])}\n"
                            elif len(row) == 2:
                                current_html_buffer += f"• {self._safe_escape(row[0])}: {self._safe_escape(row[1])}\n"
                        current_html_buffer += "\n"
                        
                    elif c_type == "callout":
                        variant = payload.get("variant", "info")
                        text = self._safe_escape(payload.get("text", ""))
                        
                        prefix = "💡"
                        if variant == "clinical_pearl":
                            prefix = "🟠"
                        elif variant == "warning":
                            prefix = "🔴"
                        elif variant == "memory_aid":
                            prefix = "🔵"
                            
                        # We use blockquote for callouts in Telegram
                        current_html_buffer += f"<blockquote>{prefix} {text}</blockquote>\n\n"
                        
                    elif c_type == "divider":
                        current_html_buffer += "──────────\n\n"
                        
                    elif c_type == "timeline":
                        events = payload.get("events", [])
                        for event in events:
                            current_html_buffer += f"⏳ <b>{self._safe_escape(event.get('time', ''))}</b>: {self._safe_escape(event.get('event', ''))}\n"
                        current_html_buffer += "\n"
                        
                    elif c_type == "math":
                        latex = self._safe_escape(payload.get("latex", ""))
                        current_html_buffer += f"<code>{latex}</code>\n\n"
                        
            elif instruction.event == RenderEvent.STREAM_COMPLETE:
                pass # End of stream
                
        return current_html_buffer.strip()
        
    def build_inline_keyboard(self, interaction_tree: InteractionTree) -> dict:
        """
        Translates the InteractionTree into a Telegram InlineKeyboardMarkup dict.
        """
        inline_keyboard = []
        # Max 4 visible actions based on Design Language
        actions_to_render = interaction_tree.actions[:4]
        
        # Build 1 button per row for simplicity
        for action in actions_to_render:
            if not action.disabled:
                inline_keyboard.append([
                    {
                        "text": action.label,
                        "callback_data": action.action_data
                    }
                ])
                
        if not inline_keyboard:
            return None
            
        return {"inline_keyboard": inline_keyboard}
