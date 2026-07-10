"""
tests/contracts/test_intent_engine_contract.py

Phase 1 - Intent Engine Contract Tests
All tests MUST FAIL before implementation exists.
Run: pytest tests/contracts/test_intent_engine_contract.py -v -W ignore::DeprecationWarning
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from interfaces import (
    IIntentEngine, IntentResult, IntentType, WorkspaceType
)

@pytest.fixture
async def intent_engine():
    """
    Provides the IntentEngine implementation under test.
    Fails until implemented.
    """
    from intent_engine.engine import IntentEngine
    return IntentEngine()

@pytest.mark.asyncio
class TestIntentEngineContract:
    
    async def test_satisfies_protocol(self, intent_engine):
        assert isinstance(intent_engine, IIntentEngine)

    async def test_classify_topic_overview(self, intent_engine):
        result = await intent_engine.classify("Tell me about ADHD")
        assert isinstance(result, IntentResult)
        assert result.intent_type == IntentType.TOPIC_OVERVIEW
        assert result.topic and "ADHD" in result.topic.upper()
        assert result.topic_type == WorkspaceType.DISEASE

    async def test_classify_topic_section(self, intent_engine):
        result = await intent_engine.classify("What are the symptoms of Asthma?")
        assert result.intent_type == IntentType.TOPIC_SECTION
        assert result.topic and "ASTHMA" in result.topic.upper()
        assert result.section == "symptoms"
        assert result.topic_type == WorkspaceType.DISEASE

    async def test_classify_drug_lookup(self, intent_engine):
        result = await intent_engine.classify("Methylphenidate")
        assert result.intent_type == IntentType.DRUG_LOOKUP
        assert result.topic and "METHYLPHENIDATE" in result.topic.upper()
        assert result.topic_type == WorkspaceType.DRUG

    async def test_classify_drug_section(self, intent_engine):
        result = await intent_engine.classify("Dosage for Lisinopril")
        assert result.intent_type == IntentType.DRUG_SECTION
        assert result.topic and "LISINOPRIL" in result.topic.upper()
        assert result.section == "dosage"
        assert result.topic_type == WorkspaceType.DRUG

    async def test_classify_clinical_case(self, intent_engine):
        result = await intent_engine.classify("Give me a clinical case for heart failure")
        assert result.intent_type == IntentType.CLINICAL_CASE
        assert result.topic and "HEART FAILURE" in result.topic.upper()

    async def test_classify_unknown_returns_safely(self, intent_engine):
        result = await intent_engine.classify("asdfghjkl")
        assert result.intent_type == IntentType.UNKNOWN
        
    async def test_never_raises(self, intent_engine):
        try:
            # Pass something that might break a naive string parser
            await intent_engine.classify(None)
        except Exception as e:
            pytest.fail(f"classify() raised {type(e).__name__}: {e}")

    async def test_main_menu(self, intent_engine):
        result = await intent_engine.classify("menu")
        assert result.intent_type == IntentType.MAIN_MENU
