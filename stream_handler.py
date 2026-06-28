import asyncio
import re
import time
import html
from aiogram.types import Message, InlineKeyboardMarkup
from aiogram.enums import ParseMode

import session_manager
import gemini_service
from streaming_formatter import format_stream_safe

def _parse_dynamic_buttons_local(text: str):
    """Local duplicate to avoid circular import with bot.py"""
    pattern = r'<BUTTONS>\s*(.+?)\s*</BUTTONS>'
    match = re.search(pattern, text, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return text.strip(), []

    body = text[:match.start()].strip() + "\n\n" + text[match.end():].strip()
    raw_buttons = match.group(1)
    
    if ',' in raw_buttons:
        buttons = [b.strip() for b in raw_buttons.split(',')]
    else:
        buttons = [b.strip() for b in raw_buttons.splitlines()]
        
    buttons = [b for b in buttons if b]
    return body.strip(), buttons


async def stream_reading_response(
    initial_message: Message,
    namespace: str,
    question: str,
    history: list,
    mode: str,
    build_keyboard_func
) -> tuple[str, bool]:
    """Streams the response, breaking into new messages upon ---"""
    
    stream = gemini_service.query_rag_stream(namespace, question, history, mode)
    
    full_answer = ""
    is_complete_final = True
    
    current_message = initial_message
    current_chunk_idx = 0
    
    last_edit_time = time.time()
    last_edit_text = ""
    
    try:
        async for chunk_text, chunk_complete in stream:
            full_answer += chunk_text
            if chunk_complete is not None:
                is_complete_final = chunk_complete
                
            # Split the accumulated answer by ---
            raw_chunks = re.split(r'\n+\s*---\s*\n+', full_answer)
            
            # If we've crossed a --- boundary, finalize the old message and create a new one!
            while current_chunk_idx < len(raw_chunks) - 1:
                # Finalize current message
                final_text = raw_chunks[current_chunk_idx].strip()
                if final_text:
                    safe_html = format_stream_safe(final_text, is_final=True)
                    if safe_html != last_edit_text:
                        try:
                            await current_message.edit_text(safe_html, parse_mode=ParseMode.HTML)
                        except Exception:
                            pass
                
                # Move to next chunk
                current_chunk_idx += 1
                last_edit_text = ""
                current_message = await current_message.answer("<i>...</i>", parse_mode=ParseMode.HTML)
            
            # Now we stream the actively growing chunk (which is the last one in raw_chunks)
            active_chunk = raw_chunks[current_chunk_idx].strip()
            if not active_chunk:
                continue
                
            now = time.time()
            if now - last_edit_time >= 0.5: # 500ms throttle
                safe_html = format_stream_safe(active_chunk, is_final=False)
                if safe_html and safe_html != last_edit_text:
                    try:
                        await current_message.edit_text(safe_html, parse_mode=ParseMode.HTML)
                        last_edit_text = safe_html
                        last_edit_time = now
                    except Exception as e:
                        # E.g. message not modified
                        pass

        # Stream finished!
        final_chunk = raw_chunks[current_chunk_idx].strip()
        
        # Look for buttons in the final chunk
        final_chunk, buttons = _parse_dynamic_buttons_local(final_chunk)
        keyboard = build_keyboard_func(buttons, namespace, include_continue=not is_complete_final)
        
        if final_chunk:
            safe_html = format_stream_safe(final_chunk, is_final=True)
            try:
                await current_message.edit_text(safe_html, parse_mode=ParseMode.HTML)
                if keyboard:
                    # We send a new distinct bubble for the buttons, OR edit it in.
                    # Based on their spec, the buttons are at the bottom.
                    # A small problem: Telegram inline buttons on long text can be hard to click if they're far up.
                    # Wait, if we edit reply_markup on the *last* streamed message bubble, it's perfect!
                    await current_message.edit_reply_markup(reply_markup=keyboard)
            except Exception:
                pass

        return full_answer, is_complete_final

    except Exception as e:
        raise e
