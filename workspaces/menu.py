from interfaces import Document, WorkspaceType, Section, Component, IASchema, ButtonSpec

class MenuWorkspace:
    def generate_screen(self, topic: str, screen_id: str) -> Document:
        nav_buttons = [
            ButtonSpec(label="📚 Books", callback_data="nav:books", tier=1),
            ButtonSpec(label="📝 Topics", callback_data="nav:topics", tier=1),
            ButtonSpec(label="⚙️ Settings", callback_data="nav:settings", tier=2),
        ]
            
        return Document(
            topic="Main Menu",
            workspace_type=WorkspaceType.MENU,
            sections=[
                Section(
                    section_id="main_menu",
                    kind="main_menu",
                    components=[
                        Component(
                            component_type="paragraph",
                            payload={"text": "👋 Welcome to Notbook! I am your AI Medical Study Assistant.\n\nType the name of a disease or drug to get started, or explore the options below."}
                        )
                    ]
                )
            ],
            ia_schema=IASchema(
                workspace_type=WorkspaceType.MENU,
                topic="Main Menu",
                nav_buttons=nav_buttons
            )
        )
