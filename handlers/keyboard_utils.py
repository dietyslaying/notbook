from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from interfaces import TelegramKeyboard

def to_aiogram_keyboard(kb: TelegramKeyboard | None) -> InlineKeyboardMarkup | None:
    if not kb:
        return None
    
    inline_keyboard = []
    for row in kb.rows:
        inline_row = []
        for btn in row:
            inline_row.append(InlineKeyboardButton(text=btn.text, callback_data=btn.callback_data))
        inline_keyboard.append(inline_row)
        
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
