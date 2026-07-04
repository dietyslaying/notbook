from interfaces import Document, WorkspaceType, Section, Component, IASchema, ButtonSpec

class DrugWorkspace:
    def generate_screen(self, topic: str, screen_id: str) -> Document:
        nav_buttons = []
        if screen_id == "overview":
            nav_buttons = [
                ButtonSpec(label="⚙️ Mechanism", callback_data="screen:mechanism", tier=1),
                ButtonSpec(label="🎯 Indications", callback_data="screen:indications", tier=1),
                ButtonSpec(label="⚖️ Dosage", callback_data="screen:dosage", tier=1),
                ButtonSpec(label="⚠️ Side Effects", callback_data="screen:side_effects", tier=2),
                ButtonSpec(label="🚫 Contraindications", callback_data="screen:contraindications", tier=2),
            ]
            
        return Document(
            topic=topic,
            workspace_type=WorkspaceType.DRUG,
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
                workspace_type=WorkspaceType.DRUG,
                topic=topic,
                nav_buttons=nav_buttons
            )
        )
