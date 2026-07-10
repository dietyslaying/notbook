from aiogram.types import Message
from intent_engine.engine import IntentEngine
from workspaces.disease import DiseaseWorkspace
from workspaces.drug import DrugWorkspace
from workspaces.base import MedicalWorkspace
from presentation_engine.component_policy import ComponentPolicy
from renderer.telegram_renderer import TelegramRenderer
from interfaces import IntentType

class MessageHandler:
    def __init__(self):
        self.intent_engine = IntentEngine()
        self.disease_ws = DiseaseWorkspace()
        self.drug_ws = DrugWorkspace()
        self.fallback_ws = MedicalWorkspace()

    async def handle(self, message: Message, bot):
        await bot.send_chat_action(message.chat.id, "typing")
        user_query = message.text
        
        # 1. Intent Routing
        intent = await self.intent_engine.classify(user_query)
        
        # 2. Workspace Processing (RAG + LLM)
        if intent == IntentType.DISEASE:
            ndm_data = await self.disease_ws.process(user_query)
        elif intent == IntentType.DRUG:
            ndm_data = await self.drug_ws.process(user_query)
        else:
            ndm_data = await self.fallback_ws.process(user_query)
            
        # 3. Presentation Engine (Map to UI Components)
        components = ComponentPolicy.map_to_ui_components(ndm_data)
        
        # 4. Renderer (Strict HTML)
        concept_id = str(message.message_id)
        screen = TelegramRenderer.render(components, concept_id)
        
        # 5. Send (Chunking if > 4096 chars)
        final_html = "".join(screen.html_parts)
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        # Rebuild keyboard from dict to aiogram object
        markup = None
        if screen.inline_keyboard:
            aiogram_keyboard = []
            for row in screen.inline_keyboard:
                aiogram_row = []
                for btn in row:
                    aiogram_row.append(InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"]))
                aiogram_keyboard.append(aiogram_row)
            markup = InlineKeyboardMarkup(inline_keyboard=aiogram_keyboard)
            
        if len(final_html) > 4096:
            for i in range(0, len(final_html), 4096):
                await message.answer(final_html[i:i+4096], parse_mode="HTML", disable_web_page_preview=True)
        else:
            await message.answer(final_html, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
