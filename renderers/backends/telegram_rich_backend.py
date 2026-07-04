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
                        icon = payload.get("icon", "📘")
                        title = self._safe_escape(payload.get("title", ""))
                        subtitle = self._safe_escape(payload.get("subtitle", ""))
                        current_html_buffer += f"{icon} <b>{title}</b>\n"
                        if subtitle:
                            current_html_buffer += f"<i>{subtitle}</i>\n"
                        current_html_buffer += "\n"
                        
                    elif c_type == "footer_card":
                        book = self._safe_escape(payload.get("source_textbook", "Primary Text"))
                        current_html_buffer += f"📘 <b>{book}</b>\n"
                        chapter = self._safe_escape(payload.get("chapter", ""))
                        page = self._safe_escape(payload.get("page", ""))
                        if chapter and page:
                            current_html_buffer += f"{chapter}, Page {page}\n"
                        elif chapter:
                            current_html_buffer += f"Chapter {chapter}\n"
                        elif page:
                            current_html_buffer += f"Page {page}\n"
                        
                        conf = self._safe_escape(payload.get("confidence", ""))
                        if conf:
                            current_html_buffer += f"\nConfidence: {conf}\n"
                        current_html_buffer += "\n"
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
                        current_html_buffer += f"{icon} <b>{title}</b>\n\n"
                        
                    elif c_type == "subheader":
                        title = self._safe_escape(payload.get("title", ""))
                        current_html_buffer += f"<b>{title.upper()}</b>\n"
                        
                    elif c_type == "reference_card":
                        citations = payload.get("citations", [])
                        if citations:
                            current_html_buffer += "📚 <b>References</b>\n"
                            for i, c in enumerate(citations, 1):
                                current_html_buffer += f"{i}. {self._safe_escape(c)}\n"
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
                        if headers or rows:
                            # Calculate column widths
                            cols = max(len(headers), max((len(r) for r in rows), default=0))
                            widths = [0] * cols
                            
                            for i, h in enumerate(headers):
                                widths[i] = max(widths[i], len(self._safe_escape(h)))
                            for r in rows:
                                for i, cell in enumerate(r):
                                    widths[i] = max(widths[i], len(self._safe_escape(cell)))
                                    
                            out = ""
                            if headers:
                                for i, h in enumerate(headers):
                                    out += f"| {self._safe_escape(h).ljust(widths[i])} "
                                out += "|\n"
                                for i in range(cols):
                                    out += "|" + "-" * (widths[i] + 2)
                                out += "|\n"
                            
                            for r in rows:
                                for i in range(cols):
                                    cell = self._safe_escape(r[i]) if i < len(r) else ""
                                    out += f"| {cell.ljust(widths[i])} "
                                out += "|\n"
                            
                            current_html_buffer += f"<pre>{out}</pre>\n\n"
                        
                    elif c_type == "callout":
                        variant = payload.get("variant", "info")
                        text = self._safe_escape(payload.get("text", ""))
                        title = self._safe_escape(payload.get("title", ""))
                        
                        prefix = "💡"
                        if variant == "clinical_pearl":
                            prefix = "💡"
                            if not title: title = "Clinical Pearl"
                        elif variant == "warning":
                            prefix = "🔴"
                            if not title: title = "Warning"
                        elif variant == "memory_aid":
                            prefix = "🔵"
                            if not title: title = "Mnemonic"
                            
                        block_title = f"{prefix} {title}" if title else prefix
                        current_html_buffer += f"<blockquote><b>{block_title}</b>\n{text}</blockquote>\n\n"
                        
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
                        current_html_buffer += f"<blockquote>▶ <b>{title}</b>\n{text}</blockquote>\n\n"
                        
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
        Combines follow-up questions (full width) and quick actions (2 columns).
        """
        inline_keyboard = []
        
        follow_ups = [a for a in interaction_tree.actions if not a.disabled and getattr(a, "kind", "") == "follow_up"]
        quick_actions = [a for a in interaction_tree.actions if not a.disabled and getattr(a, "kind", "") != "follow_up"]
        
        # 1. Full width for follow up questions
        for fu in follow_ups[:3]:
            inline_keyboard.append([{
                "text": fu.label,
                "callback_data": fu.action_data
            }])
            
        # 2. 2-columns for quick actions
        row = []
        for action in quick_actions[:6]: # Limit to 6 quick actions
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
