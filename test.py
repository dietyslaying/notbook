import html
import re

def format_for_telegram(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    text = re.sub(r'^&gt;\s*(.+)$', r'<blockquote>\1</blockquote>', text, flags=re.MULTILINE)
    text = re.sub(r'```(?:\w+)?\n(.*?)```', r'<pre>\1</pre>', text, flags=re.DOTALL)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    text = re.sub(r'^\* ', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'^- ', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'(?<!\*)\*(?!\*)', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

sample = '''ADHD is **bold** and cool.
> This is a quote.
And a list:
- One
* Two
'''
print(repr(format_for_telegram(sample)))
