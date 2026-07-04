from interfaces import Document, WorkspaceType, Section, Component, IASchema, ButtonSpec

class AnatomyWorkspace:
    def generate_screen(self, topic: str, screen_id: str) -> Document:
        nav_buttons = []
        if screen_id == "overview":
            nav_buttons = [
                ButtonSpec(label="⬅️ Back", callback_data="nav:back", tier=4),
                ButtonSpec(label="🏠 Menu", callback_data="nav:menu", tier=4),
            ]
            
        return Document(
            topic=topic,
            workspace_type=WorkspaceType.ANATOMY,
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
                workspace_type=WorkspaceType.ANATOMY,
                topic=topic,
                nav_buttons=nav_buttons
            )
        )
