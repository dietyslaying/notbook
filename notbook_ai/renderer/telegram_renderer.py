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
                    html_parts.append("<ul>")
                    for fact in facts:
                        html_part = html.escape(str(fact))
                        html_part = html_part.replace('*', '') # Strip any stray markdown
                        html_parts.append(f"<li>{html_part}</li>")
                    html_parts.append("</ul>\n")
                    
            elif comp.component_type == "collapsible":
                details = str(comp.data).replace('*', '') # Strip stray markdown
                if details:
                    html_parts.append(f"<details><summary>📋 Expand Details</summary>\n{details}\n</details>\n\n")
                    
            elif comp.component_type == "source":
                source = html.escape(str(comp.data))
                html_parts.append(f"<blockquote>{source}</blockquote>")

        # MAX 2 BUTTONS FOR ADHD DECISION PARALYSIS
        keyboard.append([
            {"text": "🧠 Quiz Me", "callback_data": f"quiz_{concept_id}"},
            {"text": "📖 Deep Dive", "callback_data": f"deep_{concept_id}"}
        ])
        
        return TelegramScreen(html_parts=html_parts, inline_keyboard=keyboard)
