"""
rich_api.py — Deterministic Markdown → Telegram RichMessage formatter.

Converts structured Markdown (from Gemini) into Bot API 10.1 RichMessage JSON,
then sends via bot.send_rich_message(). This is the SINGLE source of truth
for all message formatting in the bot.
"""
import os
import re
import logging
import aiohttp
import mistune

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Inline text parser (Markdown AST → RichText objects)
# ---------------------------------------------------------------------------

def _parse_rich_text(children: list) -> dict | list | str:
    """Recursively parse inline mistune AST to RichText objects."""
    if not children:
        return {"type": "plain", "text": "\u200b"}
    
    parts = []
    for node in children:
        t = node['type']
        if t == 'text':
            raw = node.get('raw', '')
            if not raw:
                raw = "\u200b"
            parts.append({"type": "plain", "text": raw})
        elif t == 'strong':
            parts.append({"type": "bold", "text": _parse_rich_text(node.get('children', []))})
        elif t == 'emphasis':
            parts.append({"type": "italic", "text": _parse_rich_text(node.get('children', []))})
        elif t == 'strikethrough':
            parts.append({"type": "strikethrough", "text": _parse_rich_text(node.get('children', []))})
        elif t == 'codespan':
            parts.append({"type": "code", "text": {"type": "plain", "text": node.get('raw', '')}})
        elif t == 'link':
            parts.append({"type": "text_url", "text": _parse_rich_text(node.get('children', [])), "url": node.get('attrs', {}).get('url', '')})
        elif t == 'inline_math':
            parts.append({"type": "mathematical_expression", "text": node.get('raw', '')})
        else:
            # Fallback for unsupported inline types
            if 'children' in node:
                result = _parse_rich_text(node['children'])
                if isinstance(result, list):
                    parts.extend(result)
                else:
                    parts.append(result)
            elif 'raw' in node:
                raw = node['raw']
                if not raw:
                    raw = "\u200b"
                parts.append({"type": "plain", "text": raw})
    
    if not parts:
        return {"type": "plain", "text": "\u200b"}
        
    if len(parts) == 1:
        return parts[0]
    return parts


# ---------------------------------------------------------------------------
# Block parser (Markdown AST → RichBlock objects)
# ---------------------------------------------------------------------------

def _ensure_blocks(parsed_blocks):
    if not parsed_blocks:
        return [{"type": "paragraph", "text": {"type": "plain", "text": "\u200b"}}]
    return parsed_blocks


def _parse_blocks(ast: list) -> list[dict]:
    """Recursively parse block mistune AST to RichBlock objects."""
    blocks = []
    for node in ast:
        t = node['type']
        
        if t == 'heading':
            blocks.append({
                "type": "section_heading",
                "text": _parse_rich_text(node.get('children', []))
            })
            
        elif t == 'paragraph':
            blocks.append({
                "type": "paragraph",
                "text": _parse_rich_text(node.get('children', []))
            })
            
        elif t == 'thematic_break':
            blocks.append({"type": "divider"})
            
        elif t == 'block_quote':
            # Check if this is a pull quotation (starts with ⚠️, 💡, 📌, or [!TIP] etc.)
            inner_blocks = _parse_blocks(node.get('children', []))
            is_pull = _detect_pull_quotation(inner_blocks)
            
            if is_pull:
                blocks.append({
                    "type": "pull_quotation",
                    "blocks": _ensure_blocks(inner_blocks)
                })
            else:
                blocks.append({
                    "type": "block_quotation",
                    "blocks": _ensure_blocks(inner_blocks)
                })
            
        elif t == 'block_code':
            lang = node.get('attrs', {}).get('info')
            raw = node.get('raw') or '\u200b'
            blocks.append({
                "type": "preformatted",
                "text": {"type": "plain", "text": raw},
                "language": lang if lang else ""
            })
            
        elif t == 'block_math':
            raw = node.get('raw') or '\u200b'
            blocks.append({
                "type": "mathematical_expression",
                "expression": raw
            })
            
        elif t == 'list':
            list_items = []
            ordered = node.get('attrs', {}).get('ordered', False)
            start = node.get('attrs', {}).get('start', 1)
            
            for i, item in enumerate(node.get('children', [])):
                if item['type'] != 'list_item': continue
                
                label = str(start + i) + "." if ordered else "•"
                
                # Handling checkboxes (GitHub style task lists [ ] / [x])
                is_checked = False
                has_checkbox = False
                item_children = item.get('children', [])
                
                if item_children and item_children[0]['type'] == 'block_text':
                    first_text_node = item_children[0].get('children', [])
                    if first_text_node and first_text_node[0]['type'] == 'text':
                        text_val = first_text_node[0]['raw']
                        if text_val.startswith('[ ] '):
                            has_checkbox = True
                            first_text_node[0]['raw'] = text_val[4:]
                        elif text_val.startswith('[x] ') or text_val.startswith('[X] '):
                            has_checkbox = True
                            is_checked = True
                            first_text_node[0]['raw'] = text_val[4:]

                li_block = {
                    "type": "list_item",
                    "blocks": _ensure_blocks(_parse_blocks(item_children)),
                    "label": label
                }
                if has_checkbox:
                    li_block["has_checkbox"] = True
                    li_block["is_checked"] = is_checked
                    
                list_items.append(li_block)
                
            if list_items:
                blocks.append({
                    "type": "list",
                    "items": list_items
                })
            
        elif t == 'table':
            cells = []
            for child in node.get('children', []):
                is_header = child['type'] == 'table_head'
                for row in child.get('children', []):  # table_row
                    row_cells = []
                    for cell in row.get('children', []):  # table_cell
                        align = cell.get('attrs', {}).get('align')
                        cell_data = {
                            "type": "table_cell",
                            "is_header": is_header,
                            "blocks": _ensure_blocks(_parse_blocks(cell.get('children', [])))
                        }
                        if align:
                            cell_data["align"] = align
                        row_cells.append(cell_data)
                    if row_cells:
                        cells.extend(row_cells)
                    
            if cells:
                blocks.append({
                    "type": "table",
                    "cells": cells,
                    "is_bordered": True
                })

        elif t == 'block_html':
            # Handle <details><summary>...</summary>...</details> blocks
            raw = node.get('raw', '')
            details_match = re.search(
                r'<details>\s*<summary>(.*?)</summary>(.*?)</details>',
                raw, flags=re.DOTALL | re.IGNORECASE
            )
            if details_match:
                summary_text = details_match.group(1).strip()
                detail_body = details_match.group(2).strip()
                # Recursively parse the detail body as markdown
                inner_blocks = _parse_markdown_to_blocks(detail_body)
                blocks.append({
                    "type": "details",
                    "title": {"type": "plain", "text": summary_text},
                    "blocks": _ensure_blocks(inner_blocks)
                })
            else:
                # Try to extract any meaningful text from the HTML
                text = re.sub(r'<[^>]+>', '', raw).strip()
                if text:
                    blocks.append({
                        "type": "paragraph",
                        "text": {"type": "plain", "text": text}
                    })
            
        elif t == 'block_text':
            blocks.extend(_parse_blocks(node.get('children', [])))
            
    return blocks


# ---------------------------------------------------------------------------
# Semantic detection helpers
# ---------------------------------------------------------------------------

# Emoji patterns that signal a pull quotation
_PULL_QUOTE_MARKERS = {'⚠️', '⚠', '💡', '📌', '🔑', '⭐', '❗', '‼️', '🚨', '✅', '❌'}

def _detect_pull_quotation(inner_blocks: list[dict]) -> bool:
    """Check if a blockquote should be rendered as a pull quotation."""
    if not inner_blocks:
        return False
    first = inner_blocks[0]
    if first.get('type') != 'paragraph':
        return False
    
    text_obj = first.get('text', {})
    plain_text = _extract_plain_text(text_obj)
    
    # Check for alert syntax: [!TIP], [!WARNING], [!IMPORTANT], [!NOTE], [!CAUTION]
    if re.match(r'^\[!(TIP|WARNING|IMPORTANT|NOTE|CAUTION)\]', plain_text, re.IGNORECASE):
        return True
    
    # Check for leading emoji markers
    for marker in _PULL_QUOTE_MARKERS:
        if plain_text.startswith(marker):
            return True
    
    return False


def _extract_plain_text(text_obj) -> str:
    """Extract plain text from a RichText object for semantic analysis."""
    if isinstance(text_obj, str):
        return text_obj
    if isinstance(text_obj, dict):
        if text_obj.get('type') == 'plain':
            return text_obj.get('text', '')
        # Recursively extract from nested text
        return _extract_plain_text(text_obj.get('text', ''))
    if isinstance(text_obj, list):
        return ''.join(_extract_plain_text(item) for item in text_obj)
    return ''


# ---------------------------------------------------------------------------
# Post-processing: page citations → footer, long sections → details
# ---------------------------------------------------------------------------

_PAGE_CITATION_RE = re.compile(r'\*?\(p\.?\s*\d+[\d\s,–-]*\)\*?')

def _post_process_blocks(blocks: list[dict]) -> list[dict]:
    """Apply semantic enhancements after initial AST parsing."""
    result = []
    footer_citations = []
    
    for block in blocks:
        # Collect page citations from paragraphs for a consolidated footer
        if block.get('type') == 'paragraph':
            text_obj = block.get('text', {})
            plain = _extract_plain_text(text_obj)
            
            citations = _PAGE_CITATION_RE.findall(plain)
            if citations:
                for c in citations:
                    clean = c.strip('*').strip()
                    if clean not in footer_citations:
                        footer_citations.append(clean)
        
        result.append(block)
    
    # Add a consolidated footer with all page citations
    if footer_citations:
        footer_text = "References: " + ", ".join(footer_citations)
        result.append({
            "type": "footer",
            "text": {"type": "italic", "text": {"type": "plain", "text": footer_text}}
        })
    
    return result


# ---------------------------------------------------------------------------
# Main conversion entry point
# ---------------------------------------------------------------------------

def _parse_markdown_to_blocks(md_text: str) -> list[dict]:
    """Parse markdown string into RichBlock list (internal helper)."""
    md_parser = mistune.create_markdown(
        renderer=None,
        plugins=['table', 'math', 'task_lists', 'strikethrough']
    )
    ast = md_parser(md_text)
    return _parse_blocks(ast)


def markdown_to_rich_message(md_text: str) -> dict:
    """Convert standard markdown into Bot API 10.1 RichMessage JSON structure."""
    blocks = _parse_markdown_to_blocks(md_text)
    blocks = _post_process_blocks(blocks)
    return {
        "blocks": blocks
    }


# ---------------------------------------------------------------------------
# Message sender with intelligent chunking
# ---------------------------------------------------------------------------

def _chunk_blocks(all_blocks: list[dict]) -> list[list[dict]]:
    """
    Split blocks into logical message chunks.
    
    Strategy:
    - Split at dividers (---) — these become message boundaries
    - Each chunk should be a coherent section
    - Tables, lists, and details get their own context but stay with their heading
    """
    chunks = []
    current_chunk = []
    
    for block in all_blocks:
        t = block["type"]
        
        # Dividers are message boundaries — split here
        if t == "divider":
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
            continue  # Don't include the divider itself
        
        # Section headings start a new chunk (unless this is the first block)
        if t == "section_heading" and current_chunk:
            chunks.append(current_chunk)
            current_chunk = [block]
            continue
        
        current_chunk.append(block)
    
    if current_chunk:
        chunks.append(current_chunk)
    
    # If we only got 1 chunk and it has many blocks, try to split at natural boundaries
    if len(chunks) == 1 and len(chunks[0]) > 8:
        big_chunk = chunks[0]
        chunks = []
        current_chunk = []
        para_count = 0
        
        for block in big_chunk:
            current_chunk.append(block)
            if block["type"] == "paragraph":
                para_count += 1
            
            # Split every ~4 paragraphs or after a table/list
            if para_count >= 4 or (block["type"] in ("table", "list") and len(current_chunk) > 1):
                chunks.append(current_chunk)
                current_chunk = []
                para_count = 0
        
        if current_chunk:
            chunks.append(current_chunk)
    
    return chunks if chunks else [[{"type": "paragraph", "text": {"type": "plain", "text": "(No content generated)"}}]]


async def send_chunked_rich_message(
    bot,
    chat_id: int, 
    message_thread_id: int | None, 
    markdown_text: str, 
    keyboard=None
):
    """Parse markdown, chunk into logical sections, and send as rich messages."""
    import asyncio
    from aiogram.types import InputRichMessage
    
    # Parse entire markdown to RichMessage blocks
    rich_msg = markdown_to_rich_message(markdown_text)
    all_blocks = rich_msg.get("blocks", [])
    
    if not all_blocks:
        return
    
    # Split into logical message chunks
    chunks = _chunk_blocks(all_blocks)
    
    for i, chunk in enumerate(chunks):
        is_last = (i == len(chunks) - 1)
        
        try:
            native_rich = InputRichMessage.model_validate({"blocks": chunk})
            
            await bot.send_rich_message(
                chat_id=chat_id,
                message_thread_id=message_thread_id,
                rich_message=native_rich,
                reply_markup=keyboard if is_last else None
            )
        except Exception as e:
            logger.warning(f"Rich message chunk {i} failed ({e}), falling back to plain text")
            # Fallback: extract plain text from blocks and send as regular message
            fallback_text = _blocks_to_fallback_text(chunk)
            if fallback_text:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        message_thread_id=message_thread_id,
                        text=fallback_text[:4000],
                        reply_markup=keyboard if is_last else None
                    )
                except Exception as e2:
                    logger.error(f"Fallback message also failed: {e2}")
            
        if not is_last:
            await asyncio.sleep(0.8)  # Natural delay between message bubbles


def _blocks_to_fallback_text(blocks: list[dict]) -> str:
    """Convert RichBlock list back to plain text for fallback."""
    parts = []
    for block in blocks:
        t = block.get("type", "")
        if t in ("paragraph", "section_heading", "footer"):
            parts.append(_extract_plain_text(block.get("text", {})))
        elif t == "preformatted":
            parts.append(_extract_plain_text(block.get("text", {})))
        elif t in ("block_quotation", "pull_quotation", "details"):
            for sub in block.get("blocks", []):
                parts.append(_extract_plain_text(sub.get("text", {})))
        elif t == "list":
            for item in block.get("items", []):
                label = item.get("label", "•")
                for sub in item.get("blocks", []):
                    parts.append(f"{label} {_extract_plain_text(sub.get('text', {}))}")
        elif t == "table":
            parts.append("[Table]")
        elif t == "mathematical_expression":
            parts.append(block.get("expression", ""))
    return "\n\n".join(p for p in parts if p and p != "\u200b")
