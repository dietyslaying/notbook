import json
import logging
import html
import re
from typing import List, Union, Literal
from pydantic import BaseModel, Field
from aiogram.types import InputRichMessage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic Schemas for Gemini Structured Outputs
# ---------------------------------------------------------------------------

class TextElement(BaseModel):
    text: str

class HeadingBlock(BaseModel):
    type: Literal["heading"] = "heading"
    text: str

class ParagraphBlock(BaseModel):
    type: Literal["paragraph"] = "paragraph"
    text: str

class PullQuoteBlock(BaseModel):
    type: Literal["pull_quote"] = "pull_quote"
    text: str

class ListItem(BaseModel):
    text: str

class ListBlock(BaseModel):
    type: Literal["list"] = "list"
    items: List[ListItem]

class TableRow(BaseModel):
    cells: List[TextElement]

class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    rows: List[TableRow]

class MathBlock(BaseModel):
    type: Literal["math"] = "math"
    expression: str

class TelegramRichMessage(BaseModel):
    blocks: List[Union[HeadingBlock, ParagraphBlock, PullQuoteBlock, ListBlock, TableBlock, MathBlock]]
    follow_up_questions: List[str] = Field(
        description="3 questions to prompt the user to explore the topic deeper."
    )
    buttons: List[str] = Field(
        description="Dynamic action buttons like 'Quiz Me', 'Explain Simpler'."
    )


# ---------------------------------------------------------------------------
# JSON to Telegram HTML Parser
# ---------------------------------------------------------------------------

def _rich_text_to_html(text: str) -> str:
    """Escapes HTML and optionally handles basic markdown bold/italic inside text elements."""
    escaped = html.escape(text).replace("\u200b", "")
    # Allow some basic bold/italic if Gemini outputs it
    escaped = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', escaped)
    escaped = re.sub(r'\*(.+?)\*', r'<i>\1</i>', escaped)
    escaped = re.sub(r'`(.+?)`', r'<code>\1</code>', escaped)
    return escaped

def json_to_telegram_html(response_json: dict) -> str:
    """Converts the TelegramRichMessage JSON dictionary into a Telegram Bot API HTML string."""
    blocks = response_json.get("blocks", [])
    parts = []
    
    for block in blocks:
        t = block.get("type", "")
        if t == "heading":
            parts.append(f"<b>{_rich_text_to_html(block.get('text', ''))}</b>")
        elif t == "paragraph":
            parts.append(_rich_text_to_html(block.get("text", "")))
        elif t == "pull_quote":
            parts.append(f"<blockquote>{_rich_text_to_html(block.get('text', ''))}</blockquote>")
        elif t == "list":
            for item in block.get("items", []):
                text = item.get("text", "")
                parts.append(f"• {_rich_text_to_html(text)}")
        elif t == "table":
            parts.append("<code>[Table]</code>")
            for row in block.get("rows", []):
                cells = row.get("cells", [])
                cell_texts = [_rich_text_to_html(c.get("text", "")) for c in cells]
                parts.append(" | ".join(cell_texts))
        elif t == "math":
            parts.append(f"<code>{html.escape(block.get('expression', ''))}</code>")
            
    return "\n\n".join(p for p in parts if p.strip())


def parse_ai_json(json_str: str) -> tuple[str, list[str], list[str]]:
    """Extracts the rich message HTML, follow-ups, and buttons from AI JSON."""
    try:
        data = json.loads(json_str)
        html_body = json_to_telegram_html(data)
        questions = data.get("follow_up_questions", [])
        buttons = data.get("buttons", [])
        return html_body, questions, buttons
    except Exception as e:
        logger.error(f"Failed to parse AI JSON: {e}")
        # Fallback if invalid JSON
        return html.escape(json_str), [], []
