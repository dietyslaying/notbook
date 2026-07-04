import html
from typing import List, Any
from layout.components import RenderEvent
from engine.render_planner import StreamingPlan
from engine.interaction_engine import InteractionTree

class TelegramRichBackend:
    """
    Platform-specific backend for Telegram.
    Translates the agnostic RenderEvents and InteractionTree into highly stylized Telegram HTML and Inline Keyboards.
    """
    
    def _safe_escape(self, text: Any) -> str:
        if text is None:
            return ""
        return html.escape(str(text))
        
    def render_streaming_plan(self, plan: StreamingPlan) -> str:
        """
        Executes a StreamingPlan synchronously for now (placeholder for real streaming).
        Returns the final formatted HTML string.
        """
        current_html_buffer = ""
        
        for instruction in plan.instructions:
            if instruction.event == RenderEvent.ADD:
                data = instruction.data or {}
                
                # Sections no longer render their generic == TITLE == header unless explicitly requested.
                # SectionHeaderComponent handles this explicitly now.
                if "kind" in data:
                    pass
                    
                # Render Specific Components
                elif "type" in data:
                    c_type = data["type"]
                    payload = data.get("payload", {})
                    
                    if c_type == "header_card":
                        icon = payload.get("icon", "📚")
                        title = self._safe_escape(payload.get("title", ""))
                        subtitle = self._safe_escape(payload.get("subtitle", ""))
                        current_html_buffer += "━━━━━━━━━━━━━━━━━━\n"
                        current_html_buffer += f"{icon} <b>{title.upper()}</b>\n"
                        if subtitle:
                            current_html_buffer += f"<i>{subtitle}</i>\n"
                        current_html_buffer += "━━━━━━━━━━━━━━━━━━\n\n"
                        
                    elif c_type == "metadata_card":
                        current_html_buffer += "<i>Based on Provided Study Material...</i>\n\n"
                    elif c_type == "tldr":
                        text = self._safe_escape(payload.get("text", ""))
                        current_html_buffer += f"💡 <b>TL;DR:</b> {text}\n\n"
                        
                    elif c_type == "fact_grid":
                        title = self._safe_escape(payload.get("title", "QUICK FACTS"))
                        facts = payload.get("facts", {})
                        
                        current_html_buffer += f"📊 <b>{title}</b>\n"
                        for k, v in facts.items():
                            current_html_buffer += f" 🔹 <b>{self._safe_escape(k)}:</b> {self._safe_escape(v)}\n"
                        current_html_buffer += "\n"

                    elif c_type == "section_header":
                        title = self._safe_escape(payload.get("title", ""))
                        icon = payload.get("icon", "🔹")
                        current_html_buffer += f"— {icon} <b>{title.upper()}</b> —\n"
                        
                    elif c_type == "reference_card":
                        citations = payload.get("citations", [])
                        if citations:
                            current_html_buffer += "📚 <b>References</b>\n"
                            for i, c in enumerate(citations, 1):
                                current_html_buffer += f"  <pre>{i}. {self._safe_escape(c)}</pre>\n"
                            current_html_buffer += "\n"
                            
                    elif c_type == "title": # legacy generic title
                        icon = payload.get("icon", "")
                        text = self._safe_escape(payload.get("text", ""))
                        current_html_buffer += f"<b>{icon} {text}</b>\n\n"
                        
                    elif c_type == "paragraph":
                        text = self._safe_escape(payload.get("text", ""))
                        current_html_buffer += f"{text}\n\n"
                        
                    elif c_type == "checklist":
                        items = payload.get("items", [])
                        for item in items:
                            current_html_buffer += f" • {self._safe_escape(item)}\n"
                        current_html_buffer += "\n"
                        
                    elif c_type == "table":
                        headers = payload.get("headers", [])
                        rows = payload.get("rows", [])
                        if headers:
                            current_html_buffer += f"<b>{self._safe_escape(headers[0])}</b>\n"
                        for row in rows:
                            if len(row) == 3:
                                current_html_buffer += f" • {self._safe_escape(row[0])}: {self._safe_escape(row[1])} vs {self._safe_escape(row[2])}\n"
                            elif len(row) == 2:
                                current_html_buffer += f" • {self._safe_escape(row[0])}: {self._safe_escape(row[1])}\n"
                        current_html_buffer += "\n"
                        
                    elif c_type == "callout":
                        variant = payload.get("variant", "info")
                        text = self._safe_escape(payload.get("text", ""))
                        title = self._safe_escape(payload.get("title", ""))
                        
                        prefix = "💡"
                        if variant == "clinical_pearl":
                            prefix = "🟠 PEARL:"
                        elif variant == "warning":
                            prefix = "🔴 WARNING:"
                        elif variant == "memory_aid":
                            prefix = "🔵 MNEMONIC:"
                            
                        block_title = f"{prefix} {title}" if title else prefix
                        current_html_buffer += f"<blockquote><b>{block_title}</b> {text}</blockquote>\n\n"
                        
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
                        
                    elif c_type == "block_quote":
                        text = self._safe_escape(payload.get("text", ""))
                        current_html_buffer += f"<blockquote>{text}</blockquote>\n\n"
                        
                    elif c_type == "details":
                        title = self._safe_escape(payload.get("title", "Details"))
                        text = self._safe_escape(payload.get("text", ""))
                        current_html_buffer += f"<blockquote expandable><b>{title}</b>\n{text}</blockquote>\n\n"
                        
                    elif c_type == "spoiler":
                        text = self._safe_escape(payload.get("text", ""))
                        current_html_buffer += f"<tg-spoiler>{text}</tg-spoiler>\n\n"
                        
                    elif c_type == "figure":
                        caption = self._safe_escape(payload.get("caption", "Figure"))
                        current_html_buffer += f"🖼️ <b>[Figure: {caption}]</b>\n\n"
                        
                    elif c_type == "slideshow":
                        title = self._safe_escape(payload.get("title", "Slideshow"))
                        current_html_buffer += f"📽️ <b>[Slideshow: {title}]</b>\n\n"
                        
                    elif c_type == "video":
                        title = self._safe_escape(payload.get("title", "Video"))
                        current_html_buffer += f"▶️ <b>[Video: {title}]</b>\n\n"
                        
                    elif c_type == "audio":
                        title = self._safe_escape(payload.get("title", "Audio"))
                        current_html_buffer += f"🔊 <b>[Audio: {title}]</b>\n\n"

                        
            elif instruction.event == RenderEvent.STREAM_COMPLETE:
                pass # End of stream
                
        return current_html_buffer.strip()
        
    def build_inline_keyboard(self, interaction_tree: InteractionTree) -> dict:
        """
        Translates the InteractionTree into a Telegram InlineKeyboardMarkup dict.
        """
        inline_keyboard = []
        
        # We allow up to 4 actions total, built as rows of up to 2 buttons
        actions_to_render = [a for a in interaction_tree.actions if not a.disabled][:4]
        
        row = []
        for action in actions_to_render:
            row.append({
                "text": action.label,
                "callback_data": action.action_data
            })
            if len(row) == 2:
                inline_keyboard.append(row)
                row = []
                
        if row:
            inline_keyboard.append(row)
                
        if not inline_keyboard:
            return None
            
        return {"inline_keyboard": inline_keyboard}
