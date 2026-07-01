import html
from typing import Dict, Any, List

# ---------------------------------------------------------------------------
# Telegram HTML Renderer
# ---------------------------------------------------------------------------

class TelegramRenderer:
    def __init__(self):
        pass
        
    def render(self, ast_dict: Dict[str, Any]) -> str:
        """
        Takes the composed Document AST and renders it into a standard Telegram HTML string.
        """
        parts = []
        
        # Add Title
        title = ast_dict.get("title", "")
        if title:
            parts.append(f"<b>{html.escape(title).upper()}</b>")
            
        blocks = ast_dict.get("blocks", [])
        
        for block in blocks:
            b_type = block.get("type", "")
            
            if b_type == "definition":
                term = html.escape(block.get("term", ""))
                defn = html.escape(block.get("definition", ""))
                parts.append(f"<b>{term}</b>\n{defn}")
                
            elif b_type == "facts":
                btitle = html.escape(block.get("title", "Key Facts"))
                facts = block.get("facts", [])
                list_str = "\n".join([f"• {html.escape(f)}" for f in facts])
                parts.append(f"<b>{btitle}</b>\n{list_str}")
                
            elif b_type == "clinical_pearl":
                pearl = html.escape(block.get("pearl", ""))
                parts.append(f"<blockquote><b>💎 Clinical Pearl</b>\n{pearl}</blockquote>")
                
            elif b_type == "comparison_table":
                # Standard Telegram HTML does NOT support tables. 
                # We fallback to monospace <code> grids or list formats.
                btitle = html.escape(block.get("title", "Comparison"))
                
                # A simple list fallback for mobile readability
                table_lines = [f"<b>{btitle}</b>"]
                headers = block.get("headers", [])
                
                for row in block.get("rows", []):
                    row_text = []
                    for i, cell in enumerate(row):
                        header = headers[i] if i < len(headers) else ""
                        row_text.append(f"<i>{html.escape(header)}:</i> {html.escape(cell)}")
                    table_lines.append("\n".join(row_text))
                    
                parts.append("\n\n".join(table_lines))
                
            elif b_type == "checklist":
                btitle = html.escape(block.get("title", "Checklist"))
                items = block.get("items", [])
                list_str = "\n".join([f"☐ {html.escape(item)}" for item in items])
                parts.append(f"<b>{btitle}</b>\n{list_str}")
                
            elif b_type == "section":
                btitle = html.escape(block.get("title", ""))
                paragraphs = block.get("paragraphs", [])
                p_str = "\n\n".join([html.escape(p) for p in paragraphs])
                if btitle:
                    parts.append(f"<b>{btitle}</b>\n{p_str}")
                else:
                    parts.append(p_str)
                    
            elif b_type == "reference":
                source = html.escape(block.get("source", ""))
                page = html.escape(block.get("page", ""))
                excerpt = html.escape(block.get("excerpt", ""))
                
                ref_text = f"📚 <i>Source: {source} (p. {page})</i>"
                if excerpt:
                    ref_text += f"\n<blockquote expandable>{excerpt}</blockquote>"
                parts.append(ref_text)
                
        # In standard Telegram HTML, `\n\n` separates paragraphs successfully.
        return "\n\n".join(parts)
