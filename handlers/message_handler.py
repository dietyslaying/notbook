import logging
from interfaces import IntentType, WorkspaceType, BotState, UserMode
from handlers.keyboard_utils import to_aiogram_keyboard

logger = logging.getLogger(__name__)

async def handle_start_command(
    message,
    session_manager,
    menu_workspace,
    renderer,
    **kwargs
):
    user_id = message.from_user.id
    
    session = await session_manager.create(
        user_id=user_id,
        topic="Main Menu",
        workspace_type=WorkspaceType.MENU,
        user_mode=UserMode.STUDENT
    )
    session.current_state = BotState.MAIN_MENU
    await session_manager.update(session)
    
    doc = menu_workspace.generate_screen(topic="Main Menu", screen_id="main")
    screen = renderer.render(doc)
    await message.answer(screen.html, reply_markup=to_aiogram_keyboard(screen.keyboard))


async def handle_text_message(
    message,
    intent_engine,
    session_manager,
    disease_workspace,
    drug_workspace,
    renderer,
    **kwargs
):
    text = message.text or ""
    user_id = message.from_user.id
    
    # 1. Classify intent
    intent = await intent_engine.classify(text)
    
    if intent.intent_type == IntentType.UNKNOWN:
        await message.answer("I couldn't understand that. Try asking about a disease or drug.")
        return

    # 2. Create session
    session = await session_manager.create(
        user_id=user_id,
        topic=intent.topic,
        workspace_type=intent.topic_type,
        user_mode=UserMode.STUDENT
    )
    
    # 3. Handle specific intent
    if intent.intent_type == IntentType.TOPIC_OVERVIEW and intent.topic_type == WorkspaceType.DISEASE:
        session.current_state = BotState.WORKSPACE_DISEASE_OVERVIEW
        await session_manager.update(session)
        doc = disease_workspace.generate_screen(topic=intent.topic, screen_id="overview")
        screen = renderer.render(doc)
        await message.answer(screen.html)
