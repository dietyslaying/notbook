from interfaces import Document, WorkspaceType, Section, Component, IASchema, ButtonSpec

class MenuWorkspace:
    def generate_screen(self, topic: str, screen_id: str) -> Document:
        if screen_id == "books":
            return Document(
                topic="Books",
                workspace_type=WorkspaceType.MENU,
                sections=[
                    Section(section_id="books", kind="books", components=[
                        Component(component_type="paragraph", payload={"text": "📚 <b>Books Library</b> is coming soon!"})
                    ])
                ],
                ia_schema=IASchema(
                    workspace_type=WorkspaceType.MENU, topic="Books",
                    nav_buttons=[ButtonSpec(label="⬅️ Back", callback_data="back", tier=1)]
                )
            )
        elif screen_id == "topics":
            return Document(
                topic="Topics",
                workspace_type=WorkspaceType.MENU,
                sections=[
                    Section(section_id="topics", kind="topics", components=[
                        Component(component_type="paragraph", payload={"text": "📝 <b>Topic Browser</b> is coming soon!\n\nFor now, simply type the name of a disease or drug to get started."})
                    ])
                ],
                ia_schema=IASchema(
                    workspace_type=WorkspaceType.MENU, topic="Topics",
                    nav_buttons=[ButtonSpec(label="⬅️ Back", callback_data="back", tier=1)]
                )
            )
        elif screen_id == "settings":
            return Document(
                topic="Settings",
                workspace_type=WorkspaceType.MENU,
                sections=[
                    Section(section_id="settings", kind="settings", components=[
                        Component(component_type="paragraph", payload={"text": "⚙️ <b>Settings</b> panel is coming soon!"})
                    ])
                ],
                ia_schema=IASchema(
                    workspace_type=WorkspaceType.MENU, topic="Settings",
                    nav_buttons=[ButtonSpec(label="⬅️ Back", callback_data="back", tier=1)]
                )
            )
            
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
