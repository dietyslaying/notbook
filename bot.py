import asyncio
import logging
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from intent_engine.engine import IntentEngine
from session_manager.store import InMemoryStore
from session_manager.manager import SessionManager
from state_machine.machine import StateMachine
from workspaces.disease import DiseaseWorkspace
from workspaces.drug import DrugWorkspace
from renderer.telegram_renderer import TelegramRenderer
from handlers.message_handler import handle_text_message
from handlers.callback_handler import handle_callback

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
logging.basicConfig(level=logging.INFO)

# Dependency Injection Container
intent_engine = IntentEngine()
session_manager = SessionManager(store=InMemoryStore())
state_machine = StateMachine()
disease_workspace = DiseaseWorkspace()
drug_workspace = DrugWorkspace()
renderer = TelegramRenderer()

async def on_message(message: Message):
    await handle_text_message(
        message=message,
        intent_engine=intent_engine,
        session_manager=session_manager,
        disease_workspace=disease_workspace,
        drug_workspace=drug_workspace,
        renderer=renderer
    )

async def on_callback(callback_query: CallbackQuery):
    await handle_callback(
        callback_query=callback_query,
        session_manager=session_manager,
        state_machine=state_machine,
        disease_workspace=disease_workspace,
        drug_workspace=drug_workspace,
        renderer=renderer
    )
    await callback_query.answer()

async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")
        
    # We use HTML parse mode in our renderer
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    
    dp.message.register(on_message, F.text)
    dp.callback_query.register(on_callback)
    
    logging.info("Starting Notbook Phase 1 Bot...")
    
    # Clean up any leftover webhooks from previous legacy deployments
    await bot.delete_webhook(drop_pending_updates=True)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
