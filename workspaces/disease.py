from interfaces import Document, WorkspaceType, Section, Component, IASchema, ButtonSpec

class DiseaseWorkspace:
    def generate_screen(self, topic: str, screen_id: str) -> Document:
        nav_buttons = []
        if screen_id == "overview":
            nav_buttons = [
                ButtonSpec(label="📋 Symptoms", callback_data="screen:symptoms", tier=1),
                ButtonSpec(label="🔬 Diagnosis", callback_data="screen:diagnosis", tier=1),
                ButtonSpec(label="💊 Treatment", callback_data="screen:treatment", tier=1),
                ButtonSpec(label="📚 References", callback_data="screen:references", tier=2),
            ]
        elif screen_id == "symptoms":
            nav_buttons = [
                ButtonSpec(label="⬅️ Back", callback_data="nav:back", tier=4),
                ButtonSpec(label="🏠 Menu", callback_data="nav:menu", tier=4),
            ]
            
        return Document(
            topic=topic,
            workspace_type=WorkspaceType.DISEASE,
            sections=[
                Section(
                    section_id=screen_id,
                    kind=screen_id,
                    components=[
                        Component(
                            component_type="paragraph",
                            payload={"text": f"This is the {screen_id} screen for {topic}."}
                        )
                    ]
                )
            ],
            ia_schema=IASchema(
                workspace_type=WorkspaceType.DISEASE,
                topic=topic,
                nav_buttons=nav_buttons
            )
        )
