from typing import Any
from interfaces import (
    BotState, EventType, Event, TransitionResult, IStateMachine
)

class StateMachine(IStateMachine):
    def transition(
        self,
        current_state: BotState,
        event: Event,
        context: dict[str, Any],
    ) -> TransitionResult:
        
        # 1. Global Forbidden Rules
        if event.event_type == EventType.EVT_TEXT_MESSAGE:
            if current_state in (BotState.QUIZ_QUESTION, BotState.FLASHCARD_FRONT, BotState.FLASHCARD_BACK):
                return TransitionResult(
                    next_state=current_state,
                    actions=[],
                    is_forbidden=True,
                    reason='Text messages are ignored during active quiz or flashcard sessions.'
                )

        if current_state == BotState.LOADING:
            if event.event_type == EventType.EVT_CALLBACK_NAV:
                return TransitionResult(
                    next_state=current_state,
                    actions=[],
                    is_forbidden=True,
                    reason='Navigation is blocked while loading.'
                )

        if event.event_type == EventType.EVT_CALLBACK_ANSWER:
            if current_state != BotState.QUIZ_QUESTION:
                return TransitionResult(
                    next_state=current_state,
                    actions=[],
                    is_forbidden=True,
                    reason='Answer events are only valid during an active quiz question.'
                )

        if event.event_type == EventType.EVT_CALLBACK_REVEAL:
            if current_state != BotState.FLASHCARD_FRONT:
                return TransitionResult(
                    next_state=current_state,
                    actions=[],
                    is_forbidden=True,
                    reason='Reveal events are only valid on the front of a flashcard.'
                )

        # 2. Global Shortcuts
        if event.event_type == EventType.EVT_CALLBACK_MENU:
            return TransitionResult(next_state=BotState.MAIN_MENU, actions=['push_state'])

        # 3. State-Specific Transitions
        
        if current_state == BotState.IDLE:
            if event.event_type == EventType.EVT_TEXT_MESSAGE:
                intent = event.payload.get('intent', 'unknown')
                if intent in (
                    'topic_overview', 'topic_section', 'drug_lookup', 'drug_section',
                    'clinical_case', 'comparison', 'lab_test', 'quiz_request', 'flashcard_request'
                ):
                    return TransitionResult(next_state=BotState.LOADING, actions=['create_session', 'start_rag'])
                elif intent == 'main_menu':
                    return TransitionResult(next_state=BotState.MAIN_MENU, actions=[])
                elif intent == 'settings':
                    return TransitionResult(next_state=BotState.SETTINGS, actions=[])
                elif intent == 'bookmarks':
                    return TransitionResult(next_state=BotState.BOOKMARKS_LIST, actions=[])
            return TransitionResult(next_state=BotState.IDLE, actions=[])

        if current_state == BotState.LOADING:
            if event.event_type == EventType.EVT_LOAD_COMPLETE:
                ws_type = event.payload.get('workspace_type')
                entry = event.payload.get('entry_screen')
                
                if ws_type == 'disease':
                    if entry == 'symptoms':
                        return TransitionResult(next_state=BotState.WORKSPACE_DISEASE_SYMPTOMS, actions=['render'])
                    elif entry == 'diagnosis':
                        return TransitionResult(next_state=BotState.WORKSPACE_DISEASE_DIAGNOSIS, actions=['render'])
                    elif entry == 'treatment':
                        return TransitionResult(next_state=BotState.WORKSPACE_DISEASE_TREATMENT, actions=['render'])
                    return TransitionResult(next_state=BotState.WORKSPACE_DISEASE_OVERVIEW, actions=['render'])
                
                elif ws_type == 'drug':
                    if entry == 'dosage':
                        return TransitionResult(next_state=BotState.WORKSPACE_DRUG_DOSAGE, actions=['render'])
                    return TransitionResult(next_state=BotState.WORKSPACE_DRUG_OVERVIEW, actions=['render'])
                
                elif ws_type == 'case':
                    return TransitionResult(next_state=BotState.WORKSPACE_CASE_PRESENTATION, actions=['render'])
                elif ws_type == 'comparison':
                    return TransitionResult(next_state=BotState.WORKSPACE_COMPARISON_OVERVIEW, actions=['render'])
                elif ws_type == 'lab':
                    return TransitionResult(next_state=BotState.WORKSPACE_LAB_OVERVIEW, actions=['render'])
                elif ws_type == 'quiz':
                    return TransitionResult(next_state=BotState.QUIZ_SETUP, actions=['render'])
                elif ws_type == 'flashcard':
                    return TransitionResult(next_state=BotState.FLASHCARD_FRONT, actions=['render'])
            
            elif event.event_type == EventType.EVT_LOAD_ERROR:
                return TransitionResult(next_state=BotState.ERROR, actions=['render_error'])

            elif event.event_type == EventType.EVT_STREAM_CHUNK:
                return TransitionResult(next_state=BotState.LOADING, actions=['update_stream'])
            
            return TransitionResult(next_state=BotState.LOADING, actions=[])


        # --- DISEASE WORKSPACE ---
        disease_states = [
            BotState.WORKSPACE_DISEASE_OVERVIEW, BotState.WORKSPACE_DISEASE_SYMPTOMS,
            BotState.WORKSPACE_DISEASE_DIAGNOSIS, BotState.WORKSPACE_DISEASE_CRITERIA_DETAIL,
            BotState.WORKSPACE_DISEASE_TREATMENT, BotState.WORKSPACE_DISEASE_PATHOPHYSIOLOGY,
            BotState.WORKSPACE_DISEASE_COMPLICATIONS, BotState.WORKSPACE_DISEASE_EPIDEMIOLOGY,
            BotState.WORKSPACE_DISEASE_PROGNOSIS, BotState.WORKSPACE_DISEASE_REFERENCES
        ]

        if current_state in disease_states:
            if event.event_type == EventType.EVT_CALLBACK_NAV:
                cb = event.callback_data or ''
                if cb.startswith('screen:'):
                    screen = cb.split(':')[1]
                    if screen == 'symptoms':
                        return TransitionResult(next_state=BotState.WORKSPACE_DISEASE_SYMPTOMS, actions=['push_state', 'edit_message'])
                    elif screen == 'diagnosis':
                        return TransitionResult(next_state=BotState.WORKSPACE_DISEASE_DIAGNOSIS, actions=['push_state', 'edit_message'])
                    elif screen == 'treatment':
                        return TransitionResult(next_state=BotState.WORKSPACE_DISEASE_TREATMENT, actions=['push_state', 'edit_message'])
                    elif screen == 'criteria_detail':
                        return TransitionResult(next_state=BotState.WORKSPACE_DISEASE_CRITERIA_DETAIL, actions=['push_state', 'edit_message'])
                    elif screen == 'pathophysiology':
                        return TransitionResult(next_state=BotState.WORKSPACE_DISEASE_PATHOPHYSIOLOGY, actions=['push_state', 'edit_message'])
                    elif screen == 'epidemiology':
                        return TransitionResult(next_state=BotState.WORKSPACE_DISEASE_EPIDEMIOLOGY, actions=['push_state', 'edit_message'])
                    elif screen == 'complications':
                        return TransitionResult(next_state=BotState.WORKSPACE_DISEASE_COMPLICATIONS, actions=['push_state', 'edit_message'])
                    elif screen == 'references':
                        return TransitionResult(next_state=BotState.WORKSPACE_DISEASE_REFERENCES, actions=['push_state', 'edit_message'])
                
                elif cb.startswith('quiz:setup'):
                    return TransitionResult(next_state=BotState.QUIZ_SETUP, actions=['push_state', 'edit_message'])
                
                elif cb.startswith('flashcards:start'):
                    return TransitionResult(next_state=BotState.FLASHCARD_FRONT, actions=['push_state', 'edit_message'])

                elif cb.startswith('drug:'):
                    return TransitionResult(next_state=BotState.LOADING, actions=['push_state', 'start_rag_drug'])
                
            elif event.event_type == EventType.EVT_CALLBACK_FOLLOW_UP:
                return TransitionResult(next_state=BotState.LOADING, actions=['push_state', 'start_rag_followup'])

        # --- DRUG WORKSPACE (Similar structure applies) ---
        drug_states = [
            BotState.WORKSPACE_DRUG_OVERVIEW, BotState.WORKSPACE_DRUG_MECHANISM,
            BotState.WORKSPACE_DRUG_INDICATIONS, BotState.WORKSPACE_DRUG_DOSAGE,
            BotState.WORKSPACE_DRUG_SIDE_EFFECTS, BotState.WORKSPACE_DRUG_CONTRAINDICATIONS,
            BotState.WORKSPACE_DRUG_INTERACTIONS, BotState.WORKSPACE_DRUG_REFERENCES
        ]
        if current_state in drug_states:
            if event.event_type == EventType.EVT_CALLBACK_NAV:
                cb = event.callback_data or ''
                if cb.startswith('screen:'):
                    screen = cb.split(':')[1]
                    if screen == 'mechanism': return TransitionResult(next_state=BotState.WORKSPACE_DRUG_MECHANISM, actions=['push_state', 'edit_message'])
                    elif screen == 'indications': return TransitionResult(next_state=BotState.WORKSPACE_DRUG_INDICATIONS, actions=['push_state', 'edit_message'])
                    elif screen == 'dosage': return TransitionResult(next_state=BotState.WORKSPACE_DRUG_DOSAGE, actions=['push_state', 'edit_message'])
                    elif screen == 'side_effects': return TransitionResult(next_state=BotState.WORKSPACE_DRUG_SIDE_EFFECTS, actions=['push_state', 'edit_message'])
                    elif screen == 'contraindications': return TransitionResult(next_state=BotState.WORKSPACE_DRUG_CONTRAINDICATIONS, actions=['push_state', 'edit_message'])
                    elif screen == 'interactions': return TransitionResult(next_state=BotState.WORKSPACE_DRUG_INTERACTIONS, actions=['push_state', 'edit_message'])
                elif cb.startswith('quiz:setup'):
                    return TransitionResult(next_state=BotState.QUIZ_SETUP, actions=['push_state', 'edit_message'])

        # --- QUIZ ---
        if current_state == BotState.QUIZ_SETUP:
            if event.event_type == EventType.EVT_CALLBACK_NAV and (event.callback_data or '').startswith('quiz:start'):
                return TransitionResult(next_state=BotState.QUIZ_QUESTION, actions=['generate_quiz', 'render'])
        
        elif current_state == BotState.QUIZ_QUESTION:
            if event.event_type == EventType.EVT_CALLBACK_ANSWER:
                return TransitionResult(next_state=BotState.QUIZ_FEEDBACK, actions=['evaluate_answer', 'render_feedback'])
            elif event.event_type == EventType.EVT_CALLBACK_NAV and (event.callback_data or '') == 'quiz:end':
                return TransitionResult(next_state=BotState.QUIZ_RESULTS, actions=['render_results'])
        
        elif current_state == BotState.QUIZ_FEEDBACK:
            if event.event_type == EventType.EVT_CALLBACK_NEXT:
                if context.get('is_last_question'):
                    return TransitionResult(next_state=BotState.QUIZ_RESULTS, actions=['render_results'])
                return TransitionResult(next_state=BotState.QUIZ_QUESTION, actions=['render_next_question'])
            elif event.event_type == EventType.EVT_CALLBACK_NAV and (event.callback_data or '') == 'quiz:end':
                return TransitionResult(next_state=BotState.QUIZ_RESULTS, actions=['render_results'])
                
        elif current_state == BotState.QUIZ_RESULTS:
            if event.event_type == EventType.EVT_CALLBACK_NAV:
                cb = event.callback_data or ''
                if cb == 'quiz:review':
                    return TransitionResult(next_state=BotState.QUIZ_REVIEW, actions=['render_review'])
                elif cb == 'quiz:new':
                    return TransitionResult(next_state=BotState.QUIZ_SETUP, actions=['render_setup'])
                elif cb == 'flashcards:start':
                    return TransitionResult(next_state=BotState.FLASHCARD_FRONT, actions=['render_flashcards'])

        # --- FLASHCARDS ---
        if current_state == BotState.FLASHCARD_FRONT:
            if event.event_type == EventType.EVT_CALLBACK_REVEAL:
                return TransitionResult(next_state=BotState.FLASHCARD_BACK, actions=['render_back'])
            elif event.event_type == EventType.EVT_CALLBACK_PREV:
                return TransitionResult(next_state=BotState.FLASHCARD_FRONT, actions=['render_prev'])
            elif event.event_type == EventType.EVT_CALLBACK_NEXT:
                return TransitionResult(next_state=BotState.FLASHCARD_FRONT, actions=['render_next'])
        
        elif current_state == BotState.FLASHCARD_BACK:
            if event.event_type == EventType.EVT_CALLBACK_NEXT:
                return TransitionResult(next_state=BotState.FLASHCARD_FRONT, actions=['render_next'])
            elif event.event_type == EventType.EVT_CALLBACK_PREV:
                return TransitionResult(next_state=BotState.FLASHCARD_FRONT, actions=['render_prev'])

        # --- ERROR ---
        if current_state == BotState.ERROR:
            if event.event_type == EventType.EVT_CALLBACK_NAV and (event.callback_data or '') == 'error:retry':
                return TransitionResult(next_state=BotState.LOADING, actions=['retry'])

        # --- GLOBAL BACK HANDLING ---
        if event.event_type == EventType.EVT_CALLBACK_BACK:
            history = context.get('screen_history', [])
            if history:
                prev_state = history[-1]
                return TransitionResult(next_state=prev_state, actions=['pop_state', 'render'])
            else:
                return TransitionResult(next_state=BotState.MAIN_MENU, actions=['render'])

        return TransitionResult(next_state=current_state, actions=[])
