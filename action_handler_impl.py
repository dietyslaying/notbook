
@dp.callback_query(F.data.startswith("action_"))
async def callback_action_button(callback: CallbackQuery) -> None:
    """User tapped one of the new InteractionTree action buttons."""
    action_type = callback.data
    user_id = callback.from_user.id
    
    # Remove buttons from the triggering message
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
        
    question = ""
    if action_type == "action_quiz":
        session_manager.set_user_mode(user_id, "quiz")
        question = "Give me a short quiz to test my knowledge on this topic."
    elif action_type == "action_flashcards":
        session_manager.set_user_mode(user_id, "flashcards")
        question = "Generate flashcards for the key concepts of this topic."
    elif action_type == "action_compare":
        question = "Can you compare this condition/drug with its closest alternatives?"
    elif action_type == "action_drug_interactions":
        question = "What are the most critical drug interactions I should be aware of?"
    elif action_type == "action_bookmark":
        await callback.answer("Bookmark saved! (Not actually implemented yet)")
        return
    else:
        question = "Please tell me more about this."

    # Send the user's intent as a text bubble for UX
    try:
        await callback.message.answer(f"🗣 <i>{html.escape(question)}</i>", parse_mode=ParseMode.HTML)
    except Exception:
        pass

    await callback.answer()

    namespace = session_manager.get_user_session(user_id)
    if not namespace:
        await callback.message.answer(prompts['messages']['cache_expired'], parse_mode=ParseMode.HTML)
        return

    # Process
    await _process_question(callback.message, user_id, namespace, question)
