import os
import aiohttp
import mistune

def _parse_rich_text(children: list) -> dict | list | str:
    """Recursively parse inline mistune AST to RichText objects."""
    if not children:
        return ""
    
    parts = []
    for node in children:
        t = node['type']
        if t == 'text':
            parts.append({"type": "plain", "text": node.get('raw', '')})
        elif t == 'strong':
            parts.append({"type": "bold", "text": _parse_rich_text(node.get('children', []))})
        elif t == 'emphasis':
            parts.append({"type": "italic", "text": _parse_rich_text(node.get('children', []))})
        elif t == 'codespan':
            parts.append({"type": "code", "text": {"type": "plain", "text": node.get('raw', '')}})
        elif t == 'link':
            parts.append({"type": "text_url", "text": _parse_rich_text(node.get('children', [])), "url": node.get('attrs', {}).get('url', '')})
        elif t == 'inline_math':
            parts.append({"type": "mathematical_expression", "text": node.get('raw', '')})
        else:
            # Fallback for unsupported inline types
            if 'children' in node:
                parts.extend(_parse_rich_text(node['children']))
            elif 'raw' in node:
                parts.append({"type": "plain", "text": node['raw']})
    
    if len(parts) == 1:
        return parts[0]
    return parts

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
            blocks.append({
                "type": "block_quotation",
                "blocks": _parse_blocks(node.get('children', []))
            })
            
        elif t == 'block_code':
            lang = node.get('attrs', {}).get('info')
            blocks.append({
                "type": "preformatted",
                "text": {"type": "plain", "text": node.get('raw', '')},
                "language": lang if lang else ""
            })
            
        elif t == 'block_math':
            blocks.append({
                "type": "mathematical_expression",
                "expression": node.get('raw', '')
            })
            
        elif t == 'list':
            list_items = []
            ordered = node.get('attrs', {}).get('ordered', False)
            start = node.get('attrs', {}).get('start', 1)
            
            for i, item in enumerate(node.get('children', [])):
                if item['type'] != 'list_item': continue
                
                label = str(start + i) + "." if ordered else "•"
                
                # Handling checkboxes (GitHub style task lists [ ] / [x] inside a block_text)
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
                    "blocks": _parse_blocks(item_children),
                    "label": label
                }
                if has_checkbox:
                    li_block["has_checkbox"] = True
                    li_block["is_checked"] = is_checked
                    
                list_items.append(li_block)
                
            blocks.append({
                "type": "list",
                "items": list_items
            })
            
        elif t == 'table':
            # Mistune AST for tables has 'table_head' and 'table_body'
            cells = []
            for child in node.get('children', []):
                is_header = child['type'] == 'table_head'
                for row in child.get('children', []): # table_row
                    row_cells = []
                    for cell in row.get('children', []): # table_cell
                        align = cell.get('attrs', {}).get('align')
                        cell_data = {
                            "type": "table_cell",
                            "text": _parse_rich_text(cell.get('children', [])),
                            "is_header": is_header
                        }
                        if align:
                            cell_data["align"] = align
                        row_cells.append(cell_data)
                    cells.append(row_cells)
                    
            blocks.append({
                "type": "table",
                "cells": cells,
                "is_bordered": True
            })
            
        elif t == 'block_text':
            blocks.extend(_parse_blocks(node.get('children', [])))
            
    return blocks

def markdown_to_rich_message(md_text: str) -> dict:
    """Convert standard markdown into Bot API 10.1 RichMessage JSON structure."""
    md_parser = mistune.create_markdown(renderer=None, plugins=['table', 'math', 'task_lists'])
    ast = md_parser(md_text)
    
    blocks = _parse_blocks(ast)
    return {
        "blocks": blocks
    }

async def send_chunked_rich_message(
    bot,
    chat_id: int, 
    message_thread_id: int | None, 
    markdown_text: str, 
    keyboard = None
):
    """Parse markdown, chunk into smaller message parts, and send sequentially natively."""
    import asyncio
    from aiogram.types import InputRichMessage
    
    # Parse entire AST to get all root blocks
    rich_msg = markdown_to_rich_message(markdown_text)
    all_blocks = rich_msg.get("blocks", [])
    
    if not all_blocks:
        return
        
    # Chunking strategy: send each major section or paragraph as a distinct chunk
    chunks = []
    current_chunk = []
    
    for block in all_blocks:
        t = block["type"]
        if t == "section_heading" and current_chunk:
            chunks.append(current_chunk)
            current_chunk = [block]
        elif t in ("table", "list", "block_quotation"):
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
            chunks.append([block])
        else:
            current_chunk.append(block)
            # Break off IMMEDIATELY after 1 paragraph to ensure high readability
            if len([b for b in current_chunk if b["type"] == "paragraph"]) >= 1:
                chunks.append(current_chunk)
                current_chunk = []
                
    if current_chunk:
        chunks.append(current_chunk)
        
    for i, chunk in enumerate(chunks):
        is_last = (i == len(chunks) - 1)
        
        # Validate raw dict into native aiogram InputRichMessage
        native_rich = InputRichMessage.model_validate({"blocks": chunk})
        
        await bot.send_rich_message(
            chat_id=chat_id,
            message_thread_id=message_thread_id,
            rich_message=native_rich,
            reply_markup=keyboard if is_last else None
        )
            
        if not is_last:
            await asyncio.sleep(1.0) # Natural delay for UX
