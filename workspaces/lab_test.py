from interfaces import Document, WorkspaceType, Section, Component, IASchema, ButtonSpec

class LabTestWorkspace:
    def generate_screen(self, topic: str, screen_id: str) -> Document:
        nav_buttons = []
        if screen_id == "overview":
            nav_buttons = [
                ButtonSpec(label="⬆️ High", callback_data="screen:high", tier=1),
                ButtonSpec(label="⬇️ Low", callback_data="screen:low", tier=1),
                ButtonSpec(label="💡 Significance", callback_data="screen:significance", tier=1),
                ButtonSpec(label="🔗 Related", callback_data="screen:related", tier=1),
            ]
        else:
            nav_buttons = [
                ButtonSpec(label="⬅️ Back", callback_data="nav:back", tier=4),
                ButtonSpec(label="🏠 Menu", callback_data="nav:menu", tier=4),
            ]
            
        return Document(
            topic=topic,
            workspace_type=WorkspaceType.LAB_TEST,
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
                workspace_type=WorkspaceType.LAB_TEST,
                topic=topic,
                nav_buttons=nav_buttons
            )
        )
