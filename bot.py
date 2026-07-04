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

async def on_startup(bot: Bot) -> None:
    webhook_url = f"{os.getenv('RENDER_EXTERNAL_URL')}/webhook"
    await bot.set_webhook(webhook_url)
    logging.info(f"Webhook set to: {webhook_url}")

if __name__ == "__main__":
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")
        
    # We use HTML parse mode in our renderer
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    
    dp.message.register(on_message, F.text)
    dp.callback_query.register(on_callback)
    
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    
    if render_url:
        logging.info("Running in Webhook mode (Render)...")
        from aiohttp import web
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        
        dp.startup.register(on_startup)
        
        app = web.Application()
        
        async def health(request):
            return web.Response(text="OK", status=200)
        app.router.add_get("/", health)
        
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
        setup_application(app, dp, bot=bot)
        
        port = int(os.getenv("PORT", 8000))
        web.run_app(app, host="0.0.0.0", port=port)
    else:
        logging.info("Running in Polling mode (Local)...")
        async def run_polling():
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)
            
        asyncio.run(run_polling())
