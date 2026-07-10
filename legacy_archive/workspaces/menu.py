from interfaces import Document, WorkspaceType, Section, Component, IASchema, ButtonSpec

class MenuWorkspace:
    def generate_screen(self, session, screen_id: str) -> Document:
        import gemini_service
        
        if screen_id == "books":
            books = gemini_service.get_available_books(session.user_id)
            
            nav_buttons = []
            for ns, display_name in books:
                # Add a checkmark if this is the currently selected book
                is_selected = session.metadata.get("namespace", "global|murtaghs") == ns
                label = f"{'✅ ' if is_selected else '📘 '}{display_name}"
                nav_buttons.append(ButtonSpec(label=label, callback_data=f"set_book|{ns}", tier=1))
                
            nav_buttons.append(ButtonSpec(label="⬅️ Back", callback_data="back", tier=2))
            
            return Document(
                topic="Books",
                workspace_type=WorkspaceType.MENU,
                sections=[
                    Section(section_id="books", kind="books", components=[
                        Component(component_type="paragraph", payload={"text": "📚 <b>Library</b>\n\nSelect a medical textbook to use as the primary source for your workspaces:"})
                    ])
                ],
                ia_schema=IASchema(
                    workspace_type=WorkspaceType.MENU, topic="Books",
                    nav_buttons=nav_buttons
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
            
        elif screen_id == "bookmarks":
            from session_manager.bookmark_store import BookmarkStore
            store = BookmarkStore()
            bookmarks = store.get_bookmarks(session.user_id)
            
            nav_buttons = []
            components = []
            
            if not bookmarks:
                components.append(Component(component_type="paragraph", payload={"text": "🔖 <b>Bookmarks</b>\n\nYou haven't saved any bookmarks yet."}))
            else:
                components.append(Component(component_type="paragraph", payload={"text": "🔖 <b>Bookmarks</b>\n\nSelect a bookmark to jump directly to it:"}))
                for i, b in enumerate(bookmarks):
                    label = f"{b.topic} ({b.screen_id.title()})"
                    # Since we don't have a direct workspace jump via callback yet (other than raw text),
                    # We will output this as a nav button that sets the session. Wait, if they click a bookmark, we need to rebuild that session!
                    # For now, just render them in the text.
                    nav_buttons.append(ButtonSpec(
                        label=label[:20],
                        callback_data=f"bookmark_jump|{i}",
                        tier=1
                    ))
            
            nav_buttons.append(ButtonSpec(label="⬅️ Back", callback_data="back", tier=2))
            
            return Document(
                topic="Bookmarks",
                workspace_type=WorkspaceType.MENU,
                sections=[Section(section_id="bookmarks", kind="bookmarks", components=components)],
                ia_schema=IASchema(
                    workspace_type=WorkspaceType.MENU, topic="Bookmarks",
                    nav_buttons=nav_buttons
                )
            )
            
        nav_buttons = [
            ButtonSpec(label="📚 Books", callback_data="nav:books", tier=1),
            ButtonSpec(label="🔖 Bookmarks", callback_data="nav:bookmarks", tier=1),
            ButtonSpec(label="📝 Topics", callback_data="nav:topics", tier=2),
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
