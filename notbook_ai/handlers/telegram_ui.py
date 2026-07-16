"""Helpers to send TelegramScreen payloads via aiogram."""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import config
from renderer.telegram_renderer import TelegramRenderer
from interfaces import TelegramScreen


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


async def send_screen(message: Message, screen: TelegramScreen) -> Message:
    max_chars = int(config.raw_config.get("bot", {}).get("max_message_chars", 3800))
    chunks = TelegramRenderer.chunk_html(screen.html, max_chars)
    markup = markup_from_screen(screen)
    last: Message | None = None
    for i, chunk in enumerate(chunks):
        # Attach keyboard only on the final chunk
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
    max_chars = int(config.raw_config.get("bot", {}).get("max_message_chars", 3800))
    # Callback edits are single-message; truncate carefully if needed
    html = screen.html
    if len(html) > max_chars:
        html = TelegramRenderer.chunk_html(html, max_chars)[0]
    markup = markup_from_screen(screen)
    try:
        await callback.message.edit_text(
            html,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except Exception:
        # Message not modified or too old — fall back to new message
        await callback.message.answer(
            html,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
