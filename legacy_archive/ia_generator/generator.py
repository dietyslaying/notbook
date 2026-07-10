from interfaces import IIAGenerator, KnowledgeTree, WorkspaceType, UserMode, IASchema, SectionSpec, ButtonSpec
from ia_generator.section_registry import get_allowed_sections

class IAGenerator(IIAGenerator):
    def generate(
        self,
        knowledge_tree: KnowledgeTree,
        workspace_type: WorkspaceType,
        user_mode: UserMode,
    ) -> IASchema:
        wt_value = workspace_type.value if hasattr(workspace_type, "value") else workspace_type
        allowed = get_allowed_sections(wt_value)
        sections = []
        nav_buttons = []
        
        for idx, sec_id in enumerate(allowed):
            mapped_chunk_ids = []
            
            for c in knowledge_tree.chunks:
                ctype = c.chunk_type.lower()
                
                # Intelligent mapping of block types to sections
                if sec_id == "symptoms" and ("symptom" in ctype or "clinical_case" in ctype):
                    mapped_chunk_ids.append(c.chunk_id)
                elif sec_id == "treatment" and ("treatment" in ctype or "drug" in ctype or "management" in ctype):
                    mapped_chunk_ids.append(c.chunk_id)
                elif sec_id == "references" and ("reference" in ctype or "citation" in ctype):
                    mapped_chunk_ids.append(c.chunk_id)
                elif sec_id == "complications" and "complication" in ctype:
                    mapped_chunk_ids.append(c.chunk_id)
                elif sec_id == "overview":
                    # Overview catches general concepts, comparisons, and any unmapped blocks
                    if not any(k in ctype for k in ["symptom", "clinical_case", "treatment", "drug", "management", "reference", "citation", "complication"]):
                        mapped_chunk_ids.append(c.chunk_id)
                elif sec_id == ctype:
                    # Direct match
                    mapped_chunk_ids.append(c.chunk_id)

            has_content = bool(mapped_chunk_ids)
            
            if has_content or sec_id in ("overview", "main_menu"):
                sections.append(SectionSpec(
                    section_id=sec_id,
                    section_type=sec_id,
                    has_content=has_content,
                    content_chunks=mapped_chunk_ids,
                    order=idx
                ))
                
                # Format label (e.g. "pathophysiology" -> "Pathophysiology")
                emojis = {
                    "overview": "📋", "symptoms": "🤒", "diagnosis": "🩺", 
                    "treatment": "💊", "pathophysiology": "🦠", "complications": "⚠️",
                    "presentation": "👤", "findings": "🔍", "differential": "🤔",
                    "management": "📝", "references": "📚", "mechanism": "⚙️",
                    "indications": "🎯", "dosage": "⚖️", "side_effects": "🤢",
                    "contraindications": "🚫", "interactions": "🔄", "table": "📊",
                    "differences": "⚖️", "step": "➡️", "high": "⬆️", "low": "⬇️",
                    "significance": "💡", "related": "🔗"
                }
                label = f"{emojis.get(sec_id, '🔹')} {sec_id.replace('_', ' ').title()}"
                
                nav_buttons.append(ButtonSpec(
                    label=label[:20],
                    callback_data=f"screen:{sec_id}",
                    tier=1 if idx < 4 else 2
                ))
                
        # Universal Bookmark button
        if workspace_type != WorkspaceType.MENU:
            nav_buttons.append(ButtonSpec(
                label="🔖 Bookmark",
                callback_data="bookmark:save",
                tier=3
            ))
                
        return IASchema(
            workspace_type=workspace_type,
            topic=knowledge_tree.topic,
            sections=sections,
            nav_buttons=nav_buttons,
            user_mode=user_mode
        )
