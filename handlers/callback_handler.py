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
    case_workspace,
    comparison_workspace,
    algorithm_workspace,
    lab_test_workspace,
    anatomy_workspace,
    procedure_workspace,
    renderer,
    **kwargs
):
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    # Get session
    session = await session_manager.get(user_id)
    if not session:
        return
        
    # Intercept set_book
    if data.startswith("set_book|"):
        namespace = data.split("|", 1)[1]
        session.metadata["namespace"] = namespace
        await session_manager.update(session)
        
        # Send an actual chat message to the user confirming the selection
        await callback_query.message.answer(
            f"✅ <b>Book Selected:</b> <code>{namespace}</code>\n\n"
            f"You can now type the name of any disease or drug (e.g. <i>Diabetes</i> or <i>Aspirin</i>) "
            f"to generate a workspace based on this book!"
        )
        
        await callback_query.answer("Book selected successfully!")
        
        # Navigate back to main menu
        data = "back"
        
    # Intercept bookmark
    if data == "bookmark:save":
        from session_manager.bookmark_store import BookmarkStore
        store = BookmarkStore()
        
        # Save the topic, workspace type, and current screen (extracted from current state)
        screen_id = session.current_state.name.split("_")[-1].lower()
        if screen_id in ["overview", "symptoms", "treatment", "diagnosis", "presentation", "findings", "mechanism", "dosage"]:
            # Valid screen
            pass
        else:
            screen_id = "overview"
            
        store.add_bookmark(
            user_id=user_id,
            topic=session.topic,
            workspace_type=session.workspace_type.value,
            screen_id=screen_id
        )
        await callback_query.answer(f"🔖 Bookmark saved for {session.topic}!")
        return
        
    # Intercept bookmark jump
    if data.startswith("bookmark_jump|"):
        idx = int(data.split("|")[1])
        from session_manager.bookmark_store import BookmarkStore
        store = BookmarkStore()
        bookmarks = store.get_bookmarks(user_id)
        if 0 <= idx < len(bookmarks):
            b = bookmarks[idx]
            session.topic = b.topic
            session.workspace_type = WorkspaceType(b.workspace_type)
            session.knowledge_tree = None
            session.ia_schema = None
            await session_manager.update(session)
            
            # Map workspace type to workspace object and BotState
            workspace_map = {
                WorkspaceType.DISEASE: (disease_workspace, BotState.WORKSPACE_DISEASE_OVERVIEW),
                WorkspaceType.DRUG: (drug_workspace, BotState.WORKSPACE_DRUG_OVERVIEW),
                WorkspaceType.CASE: (case_workspace, BotState.WORKSPACE_CASE_PRESENTATION),
                WorkspaceType.COMPARISON: (comparison_workspace, BotState.WORKSPACE_COMPARISON_OVERVIEW),
                WorkspaceType.ALGORITHM: (algorithm_workspace, BotState.WORKSPACE_ALGORITHM_OVERVIEW),
                WorkspaceType.LAB_TEST: (lab_test_workspace, BotState.WORKSPACE_LAB_OVERVIEW),
                WorkspaceType.ANATOMY: (anatomy_workspace, BotState.LOADING),
                WorkspaceType.PROCEDURE: (procedure_workspace, BotState.LOADING),
            }
            
            if session.workspace_type in workspace_map:
                workspace, base_state = workspace_map[session.workspace_type]
                session.current_state = BotState(f"WORKSPACE_{session.workspace_type.name}_{b.screen_id.upper()}")
                try:
                    BotState(session.current_state)
                except ValueError:
                    session.current_state = base_state
                    
                await session_manager.update(session)
                
                # Stream the new workspace
                import time
                last_edit_time = 0
                doc = None
                async for intermediate_doc in workspace.generate_screen_stream(session=session, screen_id=b.screen_id):
                    doc = intermediate_doc
                    current_time = time.time()
                    if current_time - last_edit_time > 1.5:
                        screen = renderer.render(doc)
                        try:
                            await callback_query.message.edit_text(
                                screen.html + "\n\n<i>(✍️ Loading Bookmark...)</i>",
                                reply_markup=to_aiogram_keyboard(screen.keyboard)
                            )
                            last_edit_time = current_time
                        except TelegramBadRequest:
                            pass
                
                if doc:
                    screen = renderer.render(doc)
                    try:
                        await callback_query.message.edit_text(screen.html, reply_markup=to_aiogram_keyboard(screen.keyboard))
                    except TelegramBadRequest:
                        pass
                await callback_query.answer("Jumped to bookmark!")
                return
        
        await callback_query.answer("Bookmark not found.")
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
        elif session.workspace_type == WorkspaceType.CASE:
            doc = case_workspace.generate_screen(session=session, screen_id=screen_id)
        elif session.workspace_type == WorkspaceType.COMPARISON:
            doc = comparison_workspace.generate_screen(session=session, screen_id=screen_id)
        elif session.workspace_type == WorkspaceType.ALGORITHM:
            doc = algorithm_workspace.generate_screen(session=session, screen_id=screen_id)
        elif session.workspace_type == WorkspaceType.LAB_TEST:
            doc = lab_test_workspace.generate_screen(session=session, screen_id=screen_id)
        elif session.workspace_type == WorkspaceType.ANATOMY:
            doc = anatomy_workspace.generate_screen(session=session, screen_id=screen_id)
        elif session.workspace_type == WorkspaceType.PROCEDURE:
            doc = procedure_workspace.generate_screen(session=session, screen_id=screen_id)
        elif session.workspace_type == WorkspaceType.MENU:
            doc = menu_workspace.generate_screen(session=session, screen_id=screen_id)
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
