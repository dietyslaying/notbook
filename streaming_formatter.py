import re
import html

def format_stream_safe(text: str, is_final: bool = False) -> str:
    """
    Parses a partial/streaming Markdown string into valid Telegram HTML.
    Auto-closes unclosed tags to prevent Telegram from throwing ParseMode errors.
    """
    
    # 1. Escape HTML first so user brackets don't break formatting
    text = html.escape(text)

    # Convert complete code blocks
    text = re.sub(r'```(?:\w+)?\n(.*?)```', r'<pre>\1</pre>', text, flags=re.DOTALL)
    
    # If there is an unclosed code block, format it and we stop parsing inline tags inside it
    parts = text.split('```')
    formatted_parts = []
    
    for i, part in enumerate(parts):
        if i % 2 == 1:
            # We are INSIDE a code block
            # If it's the last part and not closed (i.e. length of parts is even), we must auto-close it
            # But wait, split('```') on `foo ```bar` gives ['foo ', 'bar']. Length is 2.
            # Part index 1 is 'bar'. It's an unclosed code block.
            # We should wrap it in <pre> and NOT parse other markdown inside it.
            # Also, strip the language identifier if it's the start of the block.
            part = re.sub(r'^\w+\n', '', part)
            formatted_parts.append(f'<pre>{part}')
        else:
            # We are OUTSIDE a code block. Apply inline formatting.
            
            # **bold**
            part = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', part, flags=re.DOTALL)
            # *italic* (but not part of **)
            part = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', part, flags=re.DOTALL)
            # __underline__
            part = re.sub(r'__(.+?)__', r'<u>\1</u>', part, flags=re.DOTALL)
            # ~~strikethrough~~
            part = re.sub(r'~~(.+?)~~', r'<s>\1</s>', part, flags=re.DOTALL)
            # ||spoiler||
            part = re.sub(r'\|\|(.+?)\|\|', r'<tg-spoiler>\1</tg-spoiler>', part, flags=re.DOTALL)
            # `code`
            part = re.sub(r'`(.+?)`', r'<code>\1</code>', part, flags=re.DOTALL)
            
            # Headers
            part = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', part, flags=re.MULTILINE)
            
            # Blockquotes (standard)
            part = re.sub(r'^&gt;\s*(.+)$', r'<blockquote>\1</blockquote>', part, flags=re.MULTILINE)
            
            # Bullets
            part = re.sub(r'^\* ', '\n\n🔵 ', part, flags=re.MULTILINE)
            part = re.sub(r'^- ', '\n\n🔵 ', part, flags=re.MULTILINE)
            
            # Unclosed inline tags at the end of the stream
            unclosed_tags = []
            
            # Check for `**`
            if part.count('**') % 2 != 0:
                part = part[::-1].replace('**', '>b<', 1)[::-1] # Replace last ** with <b>
                unclosed_tags.append('</b>')
                
            # Check for `__`
            if part.count('__') % 2 != 0:
                part = part[::-1].replace('__', '>u<', 1)[::-1]
                unclosed_tags.append('</u>')
                
            # Check for `~~`
            if part.count('~~') % 2 != 0:
                part = part[::-1].replace('~~', '>s<', 1)[::-1]
                unclosed_tags.append('</s>')
                
            # Check for `||`
            if part.count('||') % 2 != 0:
                part = part[::-1].replace('||', '>reliobs-gt<', 1)[::-1]
                unclosed_tags.append('</tg-spoiler>')

            # Check for inline `
            if part.count('`') % 2 != 0:
                part = part[::-1].replace('`', '>edoc<', 1)[::-1]
                unclosed_tags.append('</code>')
                
            # Append closing tags in reverse order to properly close nested tags
            if unclosed_tags:
                part += "".join(reversed(unclosed_tags))
                
            formatted_parts.append(part)
            
    final_text = "".join(formatted_parts)
    
    # If the code block was unclosed, close it
    if len(parts) % 2 == 0:
        final_text += "</pre>"
        
    # Remove triple+ newlines
    final_text = re.sub(r'\n{3,}', '\n\n', final_text)
    
    # Strip buttons if they are partially streaming, so we don't render literal <BUTTONS> tags
    if not is_final:
        final_text = re.sub(r'&lt;BUTTONS&gt;.*', '', final_text, flags=re.DOTALL|re.IGNORECASE)
    
    return final_text.strip()
