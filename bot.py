from __future__ import annotations

import os
import re
import yaml
import logging
import asyncio
import math
import html

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

import gemini_service
import session_manager
from middlewares import RateLimitMiddleware, ContentFilterMiddleware
from rich_api import send_chunked_rich_message

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

with open("prompts.yaml", "r", encoding="utf-8") as f:
    prompts = yaml.safe_load(f)

# ---------------------------------------------------------------------------
# Bot + Dispatcher
# ---------------------------------------------------------------------------

local_api_url = config.get('bot', {}).get('telegram_local_api_url')
if local_api_url:
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(local_api_url)
    )
    bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"), session=session)
else:
    bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))

dp = Dispatcher()
dp.message.middleware(RateLimitMiddleware())
dp.message.middleware(ContentFilterMiddleware())

# ---------------------------------------------------------------------------
# Thinking animation frames (study-themed)
# ---------------------------------------------------------------------------

THINKING_FRAMES = [
    "📖  Checking the archives…",
    "🔍  Cross-referencing chapters…",
    "📚  Leafing through the pages…",
    "🗂️  Consulting the index…",
    "📝  Pulling relevant sections…",
    "🔬  Examining the material…",
    "📖  Almost there…",
    "🗃️  Retrieving from the stacks…",
    "🧠  Synthesising findings…",
    "✍️  Composing your answer…",
]

# ---------------------------------------------------------------------------
# Helpers — formatting
# ---------------------------------------------------------------------------


def format_for_telegram(text: str) -> str:
    """Convert Gemini Markdown to Telegram-safe HTML.

    Order matters: escape HTML first, then layer Markdown conversions.
    """
    text = html.escape(text)
    # **bold** → <b>bold</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # ## Headers → <b>Headers</b>
    text = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    # Blockquotes
    text = re.sub(r'^>\s*(.+)$', r'<blockquote>\1</blockquote>', text, flags=re.MULTILINE)
    # Fenced code blocks
    text = re.sub(r'```(?:\w+)?\n(.*?)```', r'<pre>\1</pre>', text, flags=re.DOTALL)
    # Inline code
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    # Bullet markers
    text = re.sub(r'^\* ', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'^- ', '• ', text, flags=re.MULTILINE)
    # Clean stray lone asterisks (single * not part of ** pairs)
    text = re.sub(r'(?<!\*)\*(?!\*)', '', text)
    # Remove triple+ newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


# ---------------------------------------------------------------------------
# Helpers — friendly errors
# ---------------------------------------------------------------------------


def get_friendly_error(error_msg: str) -> str:
    """Return a user-friendly error string — NEVER expose raw errors."""
    e = error_msg.lower()
    if "429" in e or "resource_exhausted" in e or "rate_limit" in e:
        return "⏳ High demand right now. Please wait a moment and try again."
    if "503" in e or "unavailable" in e:
        return "⏳ I'm briefly unavailable. Please try again in a few seconds."
    if "timeout" in e:
        return "⏳ That took too long. Please try a shorter question."
    return "⚠️ Something went wrong. Please try again."


# ---------------------------------------------------------------------------
# Helpers — AI formatting & logic
# ---------------------------------------------------------------------------


def parse_followups(text: str) -> tuple[str, list[str]]:
    The AI is expected to append a block like:
        📌 Related questions:
        1. Question one?
        2. Question two?
        3. Question three?
    """
    # Try to find the follow-up block
    pattern = r'📌\s*[Rr]elated questions:\s*\n((?:\s*\d+\.\s*.+\n?)+)'
    match = re.search(pattern, text)
    if not match:
        return text.strip(), []

    body = text[:match.start()].strip()
    block = match.group(1)
    questions: list[str] = []
    for line in block.strip().splitlines():
        q = re.sub(r'^\s*\d+\.\s*', '', line).strip()
        if q:
            questions.append(q)
    return body, questions[:3]


def build_followup_keyboard(
    followups: list[str],
    namespace: str,
    include_continue: bool = False,
) -> InlineKeyboardMarkup | None:
    """Build an inline keyboard with just numerical follow-up buttons + optional continue."""
    if not followups and not include_continue:
        return None

    rows: list[list[InlineKeyboardButton]] = []
    
    # Put all number buttons in one row
    if followups:
        number_row = []
        for idx in range(len(followups[:3])):
            number_row.append(InlineKeyboardButton(text=f"[{idx + 1}]", callback_data=f"fq|{idx}"))
        rows.append(number_row)
        
    if include_continue:
        rows.append([InlineKeyboardButton(text="📖  Continue reading…", callback_data=f"cont|{namespace}")])
        
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


# ---------------------------------------------------------------------------
# Helpers — quiz parsing
# ---------------------------------------------------------------------------

_QUIZ_RE = re.compile(
    r'<QUIZ>\s*'
    r'QUESTION:\s*(?P<question>.+?)\s*'
    r'A:\s*(?P<a>.+?)\s*'
    r'B:\s*(?P<b>.+?)\s*'
    r'C:\s*(?P<c>.+?)\s*'
    r'D:\s*(?P<d>.+?)\s*'
    r'CORRECT:\s*(?P<correct>[A-Da-d])\s*'
    r'EXPLANATION:\s*(?P<explanation>.+?)\s*'
    r'</QUIZ>',
    re.DOTALL,
)

_CORRECT_MAP = {'a': 0, 'b': 1, 'c': 2, 'd': 3}


def parse_quiz(text: str) -> dict | None:
    """Extract structured quiz data from AI output. Returns None on failure."""
    m = _QUIZ_RE.search(text)
    if not m:
        return None
    return {
        'question': m.group('question').strip(),
        'options': [
            m.group('a').strip(),
            m.group('b').strip(),
            m.group('c').strip(),
            m.group('d').strip(),
        ],
        'correct': _CORRECT_MAP.get(m.group('correct').strip().lower(), 0),
        'explanation': m.group('explanation').strip(),
    }


# ---------------------------------------------------------------------------
# Helpers — flashcard parsing
# ---------------------------------------------------------------------------

_FLASHCARD_RE = re.compile(
    r'<FLASHCARD>\s*'
    r'FRONT:\s*(?P<front>.+?)\s*'
    r'BACK:\s*(?P<back>.+?)\s*'
    r'</FLASHCARD>',
    re.DOTALL,
)


def parse_flashcard(text: str) -> dict | None:
    """Extract structured flashcard data from AI output. Returns None on failure."""
    m = _FLASHCARD_RE.search(text)
    if not m:
        return None
    return {
        'front': m.group('front').strip(),
        'back': m.group('back').strip(),
    }


# ---------------------------------------------------------------------------
# Helpers — animated thinking / typing
# ---------------------------------------------------------------------------


async def animated_thinking(placeholder_msg: Message, stop_event: asyncio.Event) -> None:
    """Cycle the placeholder through study phrases every 3 s until stopped."""
    idx = 0
    try:
        while not stop_event.is_set():
            await asyncio.sleep(3.2)
            if stop_event.is_set():
                break
            idx = (idx + 1) % len(THINKING_FRAMES)
            try:
                await placeholder_msg.edit_text(THINKING_FRAMES[idx])
            except Exception:
                pass
    except asyncio.CancelledError:
        pass


async def keep_typing(chat_id: int, bot_instance: Bot) -> None:
    """Send 'typing' chat action continuously until cancelled."""
    try:
        while True:
            await bot_instance.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# Helpers — keyboards
# ---------------------------------------------------------------------------


def get_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="📚 Books", callback_data="open_books")],
        [InlineKeyboardButton(text="📝 Topics", callback_data="open_modes")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_library_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    books = gemini_service.get_available_books(user_id)
    items_per_page = 8
    total_pages = math.ceil(len(books) / items_per_page) if books else 1

    start_idx = page * items_per_page
    page_books = books[start_idx : start_idx + items_per_page]

    keyboard: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for raw_ns, display_name in page_books:
        display = display_name[:28]
        btn = InlineKeyboardButton(text=f"📖 {display}", callback_data=f"book|{raw_ns}")
        row.append(btn)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"page|{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"page|{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="open_main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def continue_keyboard(namespace: str) -> InlineKeyboardMarkup:
    """Inline keyboard with a single Continue button."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖  Continue reading…", callback_data=f"cont|{namespace}")]
    ])


# ---------------------------------------------------------------------------
# Unified response sender
# ---------------------------------------------------------------------------


async def send_formatted_response(
    message: Message, text: str, user_id: int, namespace: str, is_complete: bool = True
) -> None:
    """Process followups, format HTML, and send the final static response in ADHD-friendly chunks."""

    body, followups = parse_followups(text)
    if followups:
        session_manager.set_followups(user_id, followups)
        
    keyboard = build_followup_keyboard(followups, namespace, include_continue=not is_complete)

    # HTML format the body
    html_body = format_for_telegram(body)

    # ADHD-friendly chunking: Split by double newlines, group up to ~400 chars per bubble
    paragraphs = html_body.split('\n\n')
    chunks = []
    current_chunk = ""
    
    for p in paragraphs:
        if not p.strip(): continue
        if len(current_chunk) + len(p) > 400 and current_chunk:
            chunks.append(current_chunk)
            current_chunk = p
        else:
            if current_chunk:
                current_chunk += "\n\n" + p
            else:
                current_chunk = p
                
    if current_chunk:
        chunks.append(current_chunk)
        
    if not chunks:
        chunks = ["(No content generated)"]

    # Send the chunks as separate message bubbles with a delay
    for i, chunk in enumerate(chunks):
        await message.answer(
            text=chunk,
            parse_mode=ParseMode.HTML
        )
        if i < len(chunks) - 1:
            await asyncio.sleep(1.0) # Natural delay between reading bubbles

    # Send follow-ups or continue button as a distinct, separate message bubble
    if followups or not is_complete:
        followup_text = ""
        if followups:
            followup_text = "<b>📌 Choose a related question:</b>"
        elif not is_complete:
            followup_text = "<i>The response is very long. Tap below to continue reading.</i>"

        await asyncio.sleep(1.0) # Delay before followups
        await message.answer(
            text=followup_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )


# ---------------------------------------------------------------------------
# Quiz response handler
# ---------------------------------------------------------------------------


async def handle_quiz_response(
    message: Message,
    full_answer: str,
    user_id: int,
    namespace: str,
    is_complete: bool,
) -> None:
    """Send a native Telegram quiz poll if parseable, else fall back to text."""
    quiz_data = parse_quiz(full_answer)
    if not quiz_data:
        # Fallback to regular formatted text
        await send_formatted_response(message, full_answer, user_id, namespace, is_complete)
        return

    explanation = quiz_data['explanation']
    try:
        await message.answer_poll(
            question=quiz_data['question'][:300],
            options=[opt[:100] for opt in quiz_data['options']],
            type="quiz",
            correct_option_id=quiz_data['correct'],
            explanation=explanation[:200],
            is_anonymous=False,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➡️ Next Question", callback_data="next_quiz")]
            ])
        )
    except Exception as e:
        logger.warning(f"Quiz poll failed, falling back to text: {e}")
        await send_formatted_response(message, full_answer, user_id, namespace, is_complete)


# ---------------------------------------------------------------------------
# Flashcard response handler
# ---------------------------------------------------------------------------


async def handle_flashcard_response(
    message: Message,
    full_answer: str,
    user_id: int,
    namespace: str,
    is_complete: bool,
) -> None:
    """Send the front of a flashcard with a Flip button; store the back."""
    card = parse_flashcard(full_answer)
    if not card:
        # Fallback to regular formatted text
        await send_formatted_response(message, full_answer, user_id, namespace, is_complete)
        return

    session_manager.set_flashcard_back(user_id, card['back'])

    front_html = format_for_telegram(card['front'])
    flip_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Flip to see answer", callback_data="flip")]
    ])
    await message.answer(
        f"<b>🗂️ Flashcard</b>\n\n{front_html}",
        parse_mode=ParseMode.HTML,
        reply_markup=flip_kb,
    )


# ---------------------------------------------------------------------------
# Collect full streamed response (no editing — kills ghost messages)
# ---------------------------------------------------------------------------


async def collect_full_stream(
    namespace: str,
    question: str,
    history: list,
    mode: str,
) -> tuple[str, bool]:
    """Consume query_rag_stream silently and return (full_answer, is_complete)."""
    full_answer = ""
    is_complete_final = True

    stream = gemini_service.query_rag_stream(namespace, question, history, mode)
    async for chunk_text, chunk_complete in stream:
        full_answer += chunk_text
        if chunk_complete is not None:
            is_complete_final = chunk_complete

    return full_answer, is_complete_final


# ---------------------------------------------------------------------------
# Handlers — commands
# ---------------------------------------------------------------------------


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    greeting = prompts['messages']['greeting']
    await message.answer(greeting, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())


@dp.message(Command("help", "settings"))
async def cmd_help(message: Message) -> None:
    help_text = (
        "📚 <b>NotBook Help & Settings</b>\n\n"
        "Here are the commands you can use:\n"
        "• /start - Restart the bot\n"
        "• /library or /books - Choose a book to study\n"
        "• /topics or /mode - Change your study mode (Quiz, Flashcards, etc.)\n"
        "• /help - Show this message\n\n"
        "<i>More settings features coming soon!</i>"
    )
    await message.answer(
        help_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📚 Open Library", callback_data="open_books")],
            [InlineKeyboardButton(text="🎛️ Change Study Mode", callback_data="open_modes")]
        ])
    )


@dp.message(Command("topics", "mode"))
async def cmd_topics(message: Message) -> None:
    keyboard = [
        [InlineKeyboardButton(text="💬 Normal Chat", callback_data="setmode|chat")],
        [InlineKeyboardButton(text="❓ Quiz Mode", callback_data="setmode|quiz")],
        [InlineKeyboardButton(text="🗂️ Flashcards", callback_data="setmode|flashcards")],
        [InlineKeyboardButton(text="📝 Notes", callback_data="setmode|notes")],
        [InlineKeyboardButton(text="💡 Q&A Practice", callback_data="setmode|qna")],
        [InlineKeyboardButton(text="🔄 Spaced Review", callback_data="setmode|spaced_review")],
        [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="open_main")],
    ]
    await message.answer(
        "🎛️ <b>Study Modes</b>\nChoose a mode to change how I respond:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
    )


@dp.message(Command("books", "library"))
async def cmd_books(message: Message) -> None:
    books = gemini_service.get_available_books(message.from_user.id)
    if not books:
        await message.answer("📭 The library is empty. Ask the admin to add books!")
        return
    await message.answer(
        "📚 <b>Library</b>\nSelect a book to start your study session:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_library_keyboard(message.from_user.id, 0),
    )


# ---------------------------------------------------------------------------
# Handlers — inline callbacks (menus)
# ---------------------------------------------------------------------------


@dp.callback_query(F.data == "open_main")
async def callback_open_main(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup(reply_markup=get_main_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "open_books")
async def callback_open_books(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup(
        reply_markup=get_library_keyboard(callback.from_user.id, 0),
    )
    await callback.answer()


@dp.callback_query(F.data == "open_modes")
async def callback_open_modes(callback: CallbackQuery) -> None:
    keyboard = [
        [InlineKeyboardButton(text="💬 Normal Chat", callback_data="setmode|chat")],
        [InlineKeyboardButton(text="❓ Quiz Mode", callback_data="setmode|quiz")],
        [InlineKeyboardButton(text="🗂️ Flashcards", callback_data="setmode|flashcards")],
        [InlineKeyboardButton(text="📝 Notes", callback_data="setmode|notes")],
        [InlineKeyboardButton(text="💡 Q&A Practice", callback_data="setmode|qna")],
        [InlineKeyboardButton(text="🔄 Spaced Review", callback_data="setmode|spaced_review")],
        [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="open_main")],
    ]
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@dp.callback_query(F.data.startswith("setmode|"))
async def callback_setmode(callback: CallbackQuery) -> None:
    mode = callback.data.split("|")[1]
    user_id = callback.from_user.id
    session_manager.set_user_mode(user_id, mode)

    msg = f"✅ Study Mode set to <b>{mode.replace('_', ' ').title()}</b>!\nAsk me a question to begin."
    await callback.message.edit_text(
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="open_main")]]
        ),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("page|"))
async def callback_page(callback: CallbackQuery) -> None:
    page = int(callback.data.split("|")[1])
    await callback.message.edit_reply_markup(
        reply_markup=get_library_keyboard(callback.from_user.id, page),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("book|"))
async def callback_book(callback: CallbackQuery) -> None:
    namespace = callback.data.split("|", 1)[1]
    user_id = callback.from_user.id

    # Security: verify this namespace is accessible to this user
    allowed = gemini_service.get_available_books(user_id)
    allowed_namespaces = [ns for ns, _ in allowed]
    if namespace not in allowed_namespaces:
        await callback.answer("⛔ You don't have access to this book.", show_alert=True)
        return

    session_manager.save_user_session(user_id, namespace)

    # Show just the clean book name
    if f"{user_id}|" in namespace:
        display_name = namespace.split("|", 1)[1]
    elif namespace.startswith("global|"):
        display_name = namespace[len("global|"):]
    else:
        display_name = namespace

    msg = prompts['messages']['book_selected'].format(book_name=display_name)
    await callback.message.answer(msg, parse_mode=ParseMode.HTML)
    await callback.answer()


# ---------------------------------------------------------------------------
# Handlers — follow-up question callback
# ---------------------------------------------------------------------------


@dp.callback_query(F.data.startswith("fq|"))
async def callback_followup(callback: CallbackQuery) -> None:
    """User tapped one of the three follow-up question buttons."""
    idx = int(callback.data.split("|")[1])
    user_id = callback.from_user.id
    question = session_manager.get_followup(user_id, idx)

    if not question:
        await callback.answer("Follow-up expired. Please ask a new question.", show_alert=True)
        return

    # Remove buttons from the triggering message
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()

    namespace = session_manager.get_user_session(user_id)
    if not namespace:
        await callback.message.answer(prompts['messages']['cache_expired'], parse_mode=ParseMode.HTML)
        return

    # Process exactly like a typed question
    await _process_question(callback.message, user_id, namespace, question)


# ---------------------------------------------------------------------------
# Handlers — flashcard flip callback
# ---------------------------------------------------------------------------


@dp.callback_query(F.data == "flip")
async def callback_flip(callback: CallbackQuery) -> None:
    """Reveal the back of the current flashcard."""
    user_id = callback.from_user.id
    back_text = session_manager.get_flashcard_back(user_id)

    if not back_text:
        await callback.answer("No flashcard to flip!", show_alert=True)
        return

    # Remove the flip button
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()

    back_html = format_for_telegram(back_text)
    await callback.message.answer(
        f"<b>🔄 Answer</b>\n\n{back_html}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➡️ Next Flashcard", callback_data="next_flashcard")]])
    )


# ---------------------------------------------------------------------------
# Handlers — next flashcard callback
# ---------------------------------------------------------------------------


@dp.callback_query(F.data == "next_flashcard")
async def callback_next_flashcard(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()

    namespace = session_manager.get_user_session(callback.from_user.id)
    if not namespace:
        await callback.message.answer(prompts['messages']['cache_expired'], parse_mode=ParseMode.HTML)
        return

    await _process_question(callback.message, callback.from_user.id, namespace, "Give me another flashcard on this topic")


# ---------------------------------------------------------------------------
# Handlers — next quiz callback
# ---------------------------------------------------------------------------



@dp.callback_query(F.data == "next_quiz")
async def callback_next_quiz(callback: CallbackQuery) -> None:
    """Triggered when the user wants another quiz question."""
    user_id = callback.from_user.id
    namespace = session_manager.get_user_session(user_id)
    
    if not namespace:
        await callback.answer(prompts['messages']['cache_expired'], show_alert=True)
        return

    # Simulate the user asking for another question on the topic
    question = "Ask me another quiz question on this topic, but slightly harder or exploring a different angle."
    
    await callback.answer("Generating next question...")
    
    # Process it as a normal question
    await _process_question(callback.message, user_id, namespace, question)


# ---------------------------------------------------------------------------
# Handlers — continue callback
# ---------------------------------------------------------------------------


@dp.callback_query(F.data.startswith("cont|"))
async def callback_continue(callback: CallbackQuery) -> None:
    """User pressed Continue — collect full continuation silently, then send."""
    namespace = callback.data.split("|", 1)[1]
    user_id = callback.from_user.id

    # Remove the Continue button from the triggering message
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()

    # Animated thinking placeholder
    placeholder = await callback.message.answer(THINKING_FRAMES[0])
    stop_event = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(callback.message.chat.id, bot))
    thinking_task = asyncio.create_task(animated_thinking(placeholder, stop_event))

    try:
        history = session_manager.get_chat_history(user_id)
        continuation_prompt = (
            "Please continue your previous answer. "
            "Pick up exactly where you left off and finish your explanation."
        )

        full_answer, is_complete = await collect_full_stream(
            namespace, continuation_prompt, history, session_manager.get_user_mode(user_id),
        )

        session_manager.add_to_chat_history(user_id, "user", "[continued]")
        session_manager.add_to_chat_history(user_id, "model", full_answer)

        # Stop animation & delete placeholder
        stop_event.set()
        thinking_task.cancel()
        try:
            await placeholder.delete()
        except Exception:
            pass

        await send_formatted_response(
            callback.message, full_answer, user_id, namespace, is_complete,
        )

    except Exception as e:
        stop_event.set()
        thinking_task.cancel()
        try:
            await placeholder.delete()
        except Exception:
            pass
        logger.error(f"Continue error for user {user_id}: {e}")
        await callback.message.answer(get_friendly_error(str(e)), parse_mode=ParseMode.HTML)
    finally:
        typing_task.cancel()


# ---------------------------------------------------------------------------
# Handlers — document upload
# ---------------------------------------------------------------------------


@dp.message(F.document)
async def handle_document(message: Message) -> None:
    await message.answer(
        "📁 Direct file uploads are disabled.\nUse /books to select a book from the library.",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# Handlers — main text handler
# ---------------------------------------------------------------------------


@dp.message(F.text)
async def handle_question(message: Message) -> None:
    user_id = message.from_user.id

    namespace = session_manager.get_user_session(user_id)
    if not namespace:
        await message.answer(prompts['messages']['cache_expired'], parse_mode=ParseMode.HTML)
        return

    raw_text = message.text.strip()

    # --- Number shortcut: "1", "2", "3" → select stored follow-up ---
    if raw_text in ("1", "2", "3"):
        idx = int(raw_text) - 1
        followup = session_manager.get_followup(user_id, idx)
        if followup:
            raw_text = followup

    # --- "yes" / "Yes" → continue previous topic ---
    if raw_text.lower() == "yes":
        raw_text = "Please continue with more detail on this topic"

    await _process_question(message, user_id, namespace, raw_text)


# ---------------------------------------------------------------------------
# Core question processor (shared by handle_question + follow-up callback)
# ---------------------------------------------------------------------------


async def _process_question(
    message: Message,
    user_id: int,
    namespace: str,
    question: str,
) -> None:
    """Show thinking animation, collect full response silently, dispatch to mode handler."""

    placeholder = await message.answer(THINKING_FRAMES[0])
    stop_event = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(message.chat.id, bot))
    thinking_task = asyncio.create_task(animated_thinking(placeholder, stop_event))

    try:
        history = session_manager.get_chat_history(user_id)
        mode = session_manager.get_user_mode(user_id)

        # Collect the FULL response silently — no intermediate edits
        full_answer, is_complete = await collect_full_stream(namespace, question, history, mode)

        # Truncate cleanly if cut off
        if not is_complete:
            match = re.search(r'(.+[.!?\n])', full_answer, flags=re.DOTALL)
            if match:
                full_answer = match.group(1).strip() + "..."
            else:
                full_answer = full_answer.rsplit(' ', 1)[0] + "..."

        session_manager.add_to_chat_history(user_id, "user", question)
        session_manager.add_to_chat_history(user_id, "model", full_answer)

        # Stop animation & delete placeholder
        stop_event.set()
        thinking_task.cancel()
        try:
            await placeholder.delete()
        except Exception:
            pass

        # Dispatch based on mode
        if mode == "quiz":
            await handle_quiz_response(message, full_answer, user_id, namespace, is_complete)
        elif mode == "flashcards":
            await handle_flashcard_response(message, full_answer, user_id, namespace, is_complete)
        else:
            await send_formatted_response(message, full_answer, user_id, namespace, is_complete)

    except Exception as e:
        stop_event.set()
        thinking_task.cancel()
        try:
            await placeholder.delete()
        except Exception:
            pass

        logger.error(f"Inference error for user {user_id}: {e}")
        await message.answer(get_friendly_error(str(e)), parse_mode=ParseMode.HTML)
    finally:
        typing_task.cancel()


# ---------------------------------------------------------------------------
# Webhook / Startup
# ---------------------------------------------------------------------------


async def on_startup(bot: Bot) -> None:
    webhook_url = f"{os.getenv('RENDER_EXTERNAL_URL')}/webhook"
    await bot.set_webhook(webhook_url)
    logger.info(f"Webhook set to: {webhook_url}")


async def on_shutdown(bot: Bot) -> None:
    logger.info("Shutdown initiated. Webhook left intact.")


if __name__ == "__main__":
    render_url = os.getenv("RENDER_EXTERNAL_URL")

    if render_url:
        logger.info("Running in Webhook mode (Render)...")
        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)

        app = web.Application()

        async def health(request):
            return web.Response(text="OK", status=200)
        app.router.add_get("/", health)

        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
        setup_application(app, dp, bot=bot)

        port = int(os.getenv("PORT", 8000))
        web.run_app(app, host="0.0.0.0", port=port)
    else:
        logger.info("Running in Polling mode (Local)...")
        asyncio.run(dp.start_polling(bot))
