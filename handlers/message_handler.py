import logging
from interfaces import IntentType, WorkspaceType, BotState, UserMode
from handlers.keyboard_utils import to_aiogram_keyboard
from aiogram.exceptions import TelegramBadRequest

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
    
    doc = menu_workspace.generate_screen(session=session, screen_id="main")
    screen = renderer.render(doc)
    await message.answer(screen.html, reply_markup=to_aiogram_keyboard(screen.keyboard))


async def handle_text_message(
    message,
    intent_engine,
    session_manager,
    disease_workspace,
    drug_workspace,
    case_workspace,
    comparison_workspace,
    algorithm_workspace,
    lab_test_workspace,
    anatomy_workspace,
    procedure_workspace,
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

    # 2. Get or create session
    session = await session_manager.get(user_id)
    if not session:
        session = await session_manager.create(
            user_id=user_id,
            topic=intent.topic,
            workspace_type=intent.topic_type,
            user_mode=UserMode.STUDENT
        )
    else:
        session.topic = intent.topic
        session.workspace_type = intent.topic_type
        session.knowledge_tree = None
        session.ia_schema = None
    
    # 3. Handle specific intent
    # Loading state
    loading_msg = await message.answer("🔄 <b>Generating workspace...</b>\n<i>Analyzing content...</i>")
    
    import asyncio
    import time
    from aiogram.exceptions import TelegramBadRequest
    
    # Map intent to workspace, state, and initial screen_id
    workspace_map = {
        WorkspaceType.DISEASE: (disease_workspace, BotState.WORKSPACE_DISEASE_OVERVIEW, "overview"),
        WorkspaceType.DRUG: (drug_workspace, BotState.WORKSPACE_DRUG_OVERVIEW, "overview"),
        WorkspaceType.CASE: (case_workspace, BotState.WORKSPACE_CASE_PRESENTATION, "presentation"),
        WorkspaceType.COMPARISON: (comparison_workspace, BotState.WORKSPACE_COMPARISON_OVERVIEW, "overview"),
        WorkspaceType.ALGORITHM: (algorithm_workspace, BotState.WORKSPACE_ALGORITHM_OVERVIEW, "overview"),
        WorkspaceType.LAB_TEST: (lab_test_workspace, BotState.WORKSPACE_LAB_OVERVIEW, "overview"),
        WorkspaceType.ANATOMY: (anatomy_workspace, BotState.LOADING, "overview"),
        WorkspaceType.PROCEDURE: (procedure_workspace, BotState.LOADING, "overview"),
    }
    
    if intent.topic_type not in workspace_map:
        await loading_msg.delete()
        return
        
    workspace, new_state, screen_id = workspace_map[intent.topic_type]
    
    session.current_state = new_state
    await session_manager.update(session)
    
    last_edit_time = 0
    doc = None
    
    async for intermediate_doc in workspace.generate_screen_stream(session=session, screen_id=screen_id):
        doc = intermediate_doc
        current_time = time.time()
        
        # Throttle Telegram edits to once every 1.5 seconds to avoid 429 errors
        if current_time - last_edit_time > 1.5:
            screen = renderer.render(doc)
            try:
                await loading_msg.edit_text(
                    screen.html + "\n\n<i>(✍️ Generating...)</i>", 
                    reply_markup=to_aiogram_keyboard(screen.keyboard)
                )
                last_edit_time = current_time
            except TelegramBadRequest:
                # Ignore "message is not modified" errors
                pass
                
    # Final render
    if doc:
        screen = renderer.render(doc)
        try:
            await loading_msg.edit_text(screen.html, reply_markup=to_aiogram_keyboard(screen.keyboard))
        except TelegramBadRequest:
            pass

    screen = renderer.render(doc)
    try:
        await loading_msg.edit_text(screen.html, reply_markup=to_aiogram_keyboard(screen.keyboard))
    except TelegramBadRequest:
        pass

