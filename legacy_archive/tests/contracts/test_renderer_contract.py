"""
tests/contracts/test_renderer_contract.py

Phase 1 - Renderer Contract Tests
All tests MUST FAIL before implementation exists.
Run: pytest tests/contracts/test_renderer_contract.py -v
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from interfaces import (
    IRenderer, Document, Section, Component, TelegramScreen,
    WorkspaceType, IASchema, ButtonSpec, PlatformCapabilities
)

@pytest.fixture
def renderer():
    """
    Provides the Renderer implementation under test.
    Fails until implemented.
    """
    from renderer.telegram_renderer import TelegramRenderer
    return TelegramRenderer()

class TestRendererContract:
    
    def test_satisfies_protocol(self, renderer):
        assert isinstance(renderer, IRenderer)

    def test_render_paragraph(self, renderer):
        doc = Document(
            topic="ADHD",
            workspace_type=WorkspaceType.DISEASE,
            sections=[
                Section(
                    section_id="overview",
                    kind="overview",
                    components=[
                        Component(
                            component_type="paragraph",
                            payload={"text": "ADHD is a neurodevelopmental disorder."}
                        )
                    ]
                )
            ]
        )
        screen = renderer.render(doc)
        assert isinstance(screen, TelegramScreen)
        assert "ADHD is a neurodevelopmental disorder." in screen.html

    def test_render_checklist(self, renderer):
        doc = Document(
            topic="ADHD",
            workspace_type=WorkspaceType.DISEASE,
            sections=[
                Section(
                    section_id="symptoms",
                    kind="symptoms",
                    components=[
                        Component(
                            component_type="checklist",
                            payload={"items": ["Inattention", "Hyperactivity"]}
                        )
                    ]
                )
            ]
        )
        screen = renderer.render(doc)
        assert "Inattention" in screen.html
        assert "Hyperactivity" in screen.html
        # Checklists should render with bullet points or dashes
        assert "• Inattention" in screen.html or "- Inattention" in screen.html

    def test_unknown_component_degrades_gracefully(self, renderer):
        doc = Document(
            topic="ADHD",
            workspace_type=WorkspaceType.DISEASE,
            sections=[
                Section(
                    section_id="unknown",
                    kind="unknown",
                    components=[
                        Component(
                            component_type="unknown_future_component",
                            payload={"some_data": "value"}
                        )
                    ]
                )
            ]
        )
        try:
            screen = renderer.render(doc)
            assert isinstance(screen, TelegramScreen)
        except Exception as e:
            pytest.fail(f"render() raised {type(e).__name__} on unknown component")

    def test_keyboard_generation_from_ia_schema(self, renderer):
        doc = Document(
            topic="ADHD",
            workspace_type=WorkspaceType.DISEASE,
            ia_schema=IASchema(
                workspace_type=WorkspaceType.DISEASE,
                topic="ADHD",
                nav_buttons=[
                    ButtonSpec(label="📋 Symptoms", callback_data="screen:symptoms", tier=1),
                    ButtonSpec(label="💊 Treatment", callback_data="screen:treatment", tier=1),
                    ButtonSpec(label="🏠 Menu", callback_data="nav:menu", tier=4)
                ]
            )
        )
        screen = renderer.render(doc)
        assert screen.keyboard is not None
        
        # Should build keyboard rows appropriately
        rows = screen.keyboard.rows
        assert len(rows) > 0
        
        # Find the buttons
        found_symptoms = False
        found_menu = False
        for row in rows:
            for btn in row:
                if btn.text == "📋 Symptoms" and btn.callback_data == "screen:symptoms":
                    found_symptoms = True
                if btn.text == "🏠 Menu" and btn.callback_data == "nav:menu":
                    found_menu = True
        
        assert found_symptoms
        assert found_menu

    def test_html_escaping(self, renderer):
        doc = Document(
            topic="<script>alert(1)</script>",
            workspace_type=WorkspaceType.DISEASE,
            sections=[
                Section(
                    section_id="overview",
                    kind="overview",
                    components=[
                        Component(
                            component_type="paragraph",
                            payload={"text": "Look at this <b>tag</b> & this <script>"}
                        )
                    ]
                )
            ]
        )
        screen = renderer.render(doc)
        assert "<script>" not in screen.html # Should be &lt;script&gt;
        assert "&lt;script&gt;" in screen.html
