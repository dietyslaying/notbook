import html
from interfaces import UIComponent, TelegramScreen

class TelegramRenderer:
    @staticmethod
    def render(components: list[UIComponent], concept_id: str) -> TelegramScreen:
        html_parts = []
        keyboard = []
        
        for comp in components:
            if comp.component_type == "error":
                html_parts.append(f"<b>Error</b>\n\n{html.escape(comp.data)}")
                return TelegramScreen(html_parts=html_parts, inline_keyboard=[])
                
            elif comp.component_type == "title":
                # BOLD ONLY, NO ITALICS
                title = html.escape(str(comp.data))
                html_parts.append(f"<b>{title}</b>\n\n")
                
            elif comp.component_type == "summary":
                summary = html.escape(str(comp.data))
                html_parts.append(f"{summary}\n\n")
                
            elif comp.component_type == "fact_list":
                facts = comp.data[:3] # HARD LIMIT 3
                if facts:
                    for fact in facts:
                        # Use unicode bullet instead of <ul><li> which Telegram rejects
                        fact_str = html.escape(str(fact)).replace('*', '')
                        html_parts.append(f"• {fact_str}\n")
                    html_parts.append("\n") # Spacing
                    
            elif comp.component_type == "collapsible":
                # Sanitize any stray markdown
                details = str(comp.data).replace('*', '')
                if details:
                    # Telegram uses <blockquote expandable> for collapsible text!
                    html_parts.append(f"<blockquote expandable><b>📋 Expand Details</b>\n{details}</blockquote>\n\n")
                    
            elif comp.component_type == "source":
                source = html.escape(str(comp.data))
                html_parts.append(f"<blockquote>{source}</blockquote>")

        # MAX 2 BUTTONS FOR ADHD DECISION PARALYSIS
        keyboard.append([
            {"text": "🧠 Quiz Me", "callback_data": f"quiz_{concept_id}"},
            {"text": "📖 Deep Dive", "callback_data": f"deep_{concept_id}"}
        ])
        
        return TelegramScreen(html_parts=html_parts, inline_keyboard=keyboard)
