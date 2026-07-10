
import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from interfaces import (
    BotState, EventType, Event, TransitionResult, IStateMachine, WorkspaceType
)

class TestStateMachineContract:
    def test_satisfies_protocol(self, state_machine):
        assert isinstance(state_machine, IStateMachine)

    def test_transition_is_synchronous(self, state_machine):
        import inspect
        event = Event(event_type=EventType.EVT_CALLBACK_MENU)
        result = state_machine.transition(BotState.IDLE, event, {})
        assert not inspect.isawaitable(result)

    def test_transition_never_raises(self, state_machine):
        event = Event(event_type=EventType.EVT_TEXT_MESSAGE, payload={'text': ''})
        try:
            result = state_machine.transition(BotState.IDLE, event, {})
        except Exception as e:
            pytest.fail(f'transition() raised {type(e).__name__}: {e}')

    def test_returns_transition_result(self, state_machine):
        event = Event(event_type=EventType.EVT_CALLBACK_MENU)
        result = state_machine.transition(BotState.IDLE, event, {})
        assert isinstance(result, TransitionResult)

    def test_transition_result_has_next_state(self, state_machine):
        event = Event(event_type=EventType.EVT_CALLBACK_MENU)
        result = state_machine.transition(BotState.IDLE, event, {})
        assert isinstance(result.next_state, BotState)

    def test_transition_result_actions_is_list(self, state_machine):
        event = Event(event_type=EventType.EVT_CALLBACK_MENU)
        result = state_machine.transition(BotState.IDLE, event, {})
        assert isinstance(result.actions, list)

class TestIdleTransitions:
    def test_idle_text_message_goes_to_loading(self, state_machine):
        event = Event(
            event_type=EventType.EVT_TEXT_MESSAGE,
            payload={'text': 'Tell me about ADHD', 'intent': 'topic_overview'}
        )
        result = state_machine.transition(BotState.IDLE, event, {})
        assert result.next_state == BotState.LOADING
        assert not result.is_forbidden

    def test_idle_menu_intent_goes_to_main_menu(self, state_machine):
        event = Event(
            event_type=EventType.EVT_TEXT_MESSAGE,
            payload={'intent': 'main_menu'}
        )
        result = state_machine.transition(BotState.IDLE, event, {})
        assert result.next_state == BotState.MAIN_MENU

class TestLoadingTransitions:
    def test_load_complete_disease_goes_to_overview(self, state_machine):
        event = Event(
            event_type=EventType.EVT_LOAD_COMPLETE,
            payload={'workspace_type': 'disease', 'entry_screen': 'overview'}
        )
        result = state_machine.transition(BotState.LOADING, event, {})
        assert result.next_state == BotState.WORKSPACE_DISEASE_OVERVIEW

    def test_load_error_goes_to_error(self, state_machine):
        event = Event(event_type=EventType.EVT_LOAD_ERROR)
        result = state_machine.transition(BotState.LOADING, event, {})
        assert result.next_state == BotState.ERROR

    def test_loading_blocks_nav_callbacks(self, state_machine):
        event = Event(
            event_type=EventType.EVT_CALLBACK_NAV,
            callback_data='screen:symptoms'
        )
        result = state_machine.transition(BotState.LOADING, event, {})
        assert result.is_forbidden

class TestDiseaseWorkspaceTransitions:
    def test_overview_symptoms_nav(self, state_machine):
        event = Event(
            event_type=EventType.EVT_CALLBACK_NAV,
            callback_data='screen:symptoms'
        )
        result = state_machine.transition(BotState.WORKSPACE_DISEASE_OVERVIEW, event, {})
        assert result.next_state == BotState.WORKSPACE_DISEASE_SYMPTOMS

    def test_overview_back_with_no_history_goes_to_menu(self, state_machine):
        event = Event(event_type=EventType.EVT_CALLBACK_BACK)
        result = state_machine.transition(
            BotState.WORKSPACE_DISEASE_OVERVIEW, event, {'screen_history': []}
        )
        assert result.next_state == BotState.MAIN_MENU

    def test_symptoms_back_goes_to_overview(self, state_machine):
        event = Event(event_type=EventType.EVT_CALLBACK_BACK)
        result = state_machine.transition(
            BotState.WORKSPACE_DISEASE_SYMPTOMS, event,
            {'screen_history': [BotState.WORKSPACE_DISEASE_OVERVIEW]}
        )
        assert result.next_state == BotState.WORKSPACE_DISEASE_OVERVIEW

    def test_treatment_drug_nav_goes_to_loading(self, state_machine):
        event = Event(
            event_type=EventType.EVT_CALLBACK_NAV,
            callback_data='drug:methylphenidate'
        )
        result = state_machine.transition(BotState.WORKSPACE_DISEASE_TREATMENT, event, {})
        assert result.next_state == BotState.LOADING

class TestForbiddenTransitions:
    def test_quiz_question_blocks_text_messages(self, state_machine):
        event = Event(
            event_type=EventType.EVT_TEXT_MESSAGE,
            payload={'text': 'hi'}
        )
        result = state_machine.transition(BotState.QUIZ_QUESTION, event, {})
        assert result.is_forbidden

    def test_answer_event_only_valid_in_quiz_question(self, state_machine):
        event = Event(
            event_type=EventType.EVT_CALLBACK_ANSWER,
            callback_data='answer:A'
        )
        result = state_machine.transition(BotState.WORKSPACE_DISEASE_OVERVIEW, event, {})
        assert result.is_forbidden

    def test_forbidden_has_reason(self, state_machine):
        event = Event(
            event_type=EventType.EVT_CALLBACK_NAV,
            callback_data='screen:symptoms'
        )
        result = state_machine.transition(BotState.LOADING, event, {})
        assert result.is_forbidden
        assert result.reason is not None

@pytest.fixture
def state_machine():
    from state_machine.machine import StateMachine
    return StateMachine()
