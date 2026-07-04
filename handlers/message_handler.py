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

    # 2. Create session
    session = await session_manager.create(
        user_id=user_id,
        topic=intent.topic,
        workspace_type=intent.topic_type,
        user_mode=UserMode.STUDENT
    )
    
    # 3. Handle specific intent
    # Loading state
    loading_msg = await message.answer("🔄 <b>Generating workspace...</b>\n<i>Analyzing content...</i>")
    
    if intent.topic_type == WorkspaceType.DISEASE:
        session.current_state = BotState.WORKSPACE_DISEASE_OVERVIEW
        await session_manager.update(session)
        doc = disease_workspace.generate_screen(session=session, screen_id="overview")
        
    elif intent.topic_type == WorkspaceType.DRUG:
        session.current_state = BotState.WORKSPACE_DRUG_OVERVIEW
        await session_manager.update(session)
        doc = drug_workspace.generate_screen(session=session, screen_id="overview")
        
    elif intent.topic_type == WorkspaceType.CASE:
        session.current_state = BotState.WORKSPACE_CASE_PRESENTATION
        await session_manager.update(session)
        doc = case_workspace.generate_screen(session=session, screen_id="presentation")
        
    elif intent.topic_type == WorkspaceType.COMPARISON:
        session.current_state = BotState.WORKSPACE_COMPARISON_OVERVIEW
        await session_manager.update(session)
        doc = comparison_workspace.generate_screen(session=session, screen_id="overview")
        
    elif intent.topic_type == WorkspaceType.ALGORITHM:
        session.current_state = BotState.WORKSPACE_ALGORITHM_OVERVIEW
        await session_manager.update(session)
        doc = algorithm_workspace.generate_screen(session=session, screen_id="overview")
        
    elif intent.topic_type == WorkspaceType.LAB_TEST:
        session.current_state = BotState.WORKSPACE_LAB_OVERVIEW
        await session_manager.update(session)
        doc = lab_test_workspace.generate_screen(session=session, screen_id="overview")
        
    elif intent.topic_type == WorkspaceType.ANATOMY:
        session.current_state = BotState.LOADING
        await session_manager.update(session)
        doc = anatomy_workspace.generate_screen(session=session, screen_id="overview")
        
    elif intent.topic_type == WorkspaceType.PROCEDURE:
        session.current_state = BotState.LOADING
        await session_manager.update(session)
        doc = procedure_workspace.generate_screen(session=session, screen_id="overview")
    else:
        await loading_msg.delete()
        return

    screen = renderer.render(doc)
    await loading_msg.edit_text(screen.html, reply_markup=to_aiogram_keyboard(screen.keyboard))

