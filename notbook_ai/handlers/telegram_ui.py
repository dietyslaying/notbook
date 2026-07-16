"""Helpers to send TelegramScreen payloads via aiogram (rich + HTML fallback)."""

from __future__ import annotations

import logging
import random
import time
from typing import Optional

from aiogram import Bot
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    Message,
)

from config import config
from interfaces import TelegramScreen
from renderer.telegram_renderer import TelegramRenderer

logger = logging.getLogger(__name__)


def _bot_flag(name: str, default: bool = True) -> bool:
    bot_cfg = config.raw_config.get("bot") or {}
    val = bot_cfg.get(name, default)
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "on")
    return bool(val)


def rich_enabled() -> bool:
    return _bot_flag("rich_messages", True)


def stream_drafts_enabled() -> bool:
    return _bot_flag("stream_drafts", True)


def markup_from_screen(screen: TelegramScreen) -> InlineKeyboardMarkup | None:
    if not screen.inline_keyboard:
        return None
    rows = []
    for row in screen.inline_keyboard:
        rows.append(
            [
                InlineKeyboardButton(
                    text=btn["text"],
                    callback_data=btn["callback_data"],
                )
                for btn in row
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _rich_payload(screen: TelegramScreen) -> InputRichMessage | None:
    md = (screen.rich_markdown or "").strip()
    if not md:
        return None
    return InputRichMessage(markdown=md, skip_entity_detection=True)


async def send_screen(message: Message, screen: TelegramScreen) -> Message:
    """Send final answer: prefer sendRichMessage, fall back to HTML sendMessage."""
    max_chars = int(config.raw_config.get("bot", {}).get("max_message_chars", 3800))
    markup = markup_from_screen(screen)
    bot: Bot = message.bot
    chat_id = message.chat.id

    if rich_enabled():
        rich = _rich_payload(screen)
        if rich is not None:
            try:
                return await bot.send_rich_message(
                    chat_id=chat_id,
                    rich_message=rich,
                    reply_markup=markup,
                )
            except Exception as e:
                logger.warning("send_rich_message failed, HTML fallback: %s", e)

    chunks = TelegramRenderer.chunk_html(screen.html, max_chars)
    last: Message | None = None
    for i, chunk in enumerate(chunks):
        kb = markup if i == len(chunks) - 1 else None
        last = await message.answer(
            chunk,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    assert last is not None
    return last


async def edit_screen(callback: CallbackQuery, screen: TelegramScreen) -> None:
    """Edit the callback message; prefer rich_message when available."""
    max_chars = int(config.raw_config.get("bot", {}).get("max_message_chars", 3800))
    markup = markup_from_screen(screen)
    msg = callback.message
    if msg is None:
        return
    bot: Bot = callback.bot
    chat_id = msg.chat.id
    message_id = msg.message_id

    if rich_enabled():
        rich = _rich_payload(screen)
        if rich is not None:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    rich_message=rich,
                    reply_markup=markup,
                )
                return
            except Exception as e:
                # "message is not modified" is fine; other failures fall through
                err = str(e).lower()
                if "not modified" in err:
                    return
                logger.warning("edit rich_message failed, HTML fallback: %s", e)

    html = screen.html
    if len(html) > max_chars:
        html = TelegramRenderer.chunk_html(html, max_chars)[0]
    try:
        await msg.edit_text(
            html,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except Exception as e:
        err = str(e).lower()
        if "not modified" in err:
            return
        await msg.answer(
            html,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )


def new_draft_id(user_id: int = 0) -> int:
    """Non-zero draft id for send*Draft methods."""
    base = (int(time.time() * 1000) ^ (user_id << 8) ^ random.randint(1, 1_000_000)) & 0x7FFFFFFF
    return base or 1


async def stream_draft(
    bot: Bot,
    chat_id: int,
    draft_id: int,
    *,
    markdown: Optional[str] = None,
    text: Optional[str] = None,
    message_thread_id: Optional[int] = None,
) -> bool:
    """
    Push a live draft bubble (private chats). Returns True if Telegram accepted it.
    Prefer rich draft when markdown is given; else plain sendMessageDraft.
    """
    if not stream_drafts_enabled():
        return False
    try:
        if markdown and rich_enabled():
            await bot.send_rich_message_draft(
                chat_id=chat_id,
                draft_id=draft_id,
                rich_message=InputRichMessage(
                    markdown=markdown,
                    skip_entity_detection=True,
                ),
                message_thread_id=message_thread_id,
            )
            return True
        # Empty text shows native "Thinking…" placeholder (Bot API 10.0+)
        await bot.send_message_draft(
            chat_id=chat_id,
            draft_id=draft_id,
            text=text if text is not None else "",
            message_thread_id=message_thread_id,
        )
        return True
    except Exception as e:
        # Groups / older clients / free-tier quirks — non-fatal
        logger.debug("stream_draft skipped: %s", e)
        return False
