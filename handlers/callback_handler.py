import logging
from aiogram.exceptions import TelegramBadRequest
from interfaces import BotState, WorkspaceType, Event, EventType
from handlers.keyboard_utils import to_aiogram_keyboard

logger = logging.getLogger(__name__)

async def handle_callback(
    callback_query,
    session_manager,
    state_machine,
    menu_workspace,
    disease_workspace,
    drug_workspace,
    renderer,
    **kwargs
):
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    # Get session
    session = await session_manager.get(user_id)
    if not session:
        return
        
    # Transition State
    event = Event(event_type=EventType.EVT_CALLBACK_NAV, callback_data=data)
    transition = state_machine.transition(session.current_state, event, {})
    
    if not transition.is_forbidden:
        # Push state history
        await session_manager.push_state(session, session.current_state)
        session.current_state = transition.next_state
        await session_manager.update(session)
        
        # Parse screen_id from callback (e.g. "screen:symptoms" -> "symptoms")
        screen_id = data.split(":")[-1] if ":" in data else data
        
        if session.workspace_type == WorkspaceType.DISEASE:
            doc = disease_workspace.generate_screen(session=session, screen_id=screen_id)
        elif session.workspace_type == WorkspaceType.DRUG:
            doc = drug_workspace.generate_screen(session=session, screen_id=screen_id)
        elif session.workspace_type == WorkspaceType.MENU:
            doc = menu_workspace.generate_screen(topic="Main Menu", screen_id="main")
        else:
            return
            
        screen = renderer.render(doc)
        
        # Update message
        try:
            await callback_query.message.edit_text(
                text=screen.html,
                reply_markup=to_aiogram_keyboard(screen.keyboard)
            )
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                raise
