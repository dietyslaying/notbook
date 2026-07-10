from interfaces import IPresentationEngine, IASchema, KnowledgeTree, Document, Section

class PresentationEngine(IPresentationEngine):
    def generate_document(
        self,
        ia_schema: IASchema,
        knowledge_tree: KnowledgeTree,
        screen_id: str
    ) -> Document:
        
        # Find the section spec for the requested screen_id
        target_spec = None
        for spec in ia_schema.sections:
            if spec.section_id == screen_id:
                target_spec = spec
                break
                
        sections = []
        if target_spec:
            # Map chunk_ids in the spec to actual Chunk objects
            chunk_map = {c.chunk_id: c for c in knowledge_tree.chunks}
            section_chunks = [chunk_map[c_id] for c_id in target_spec.content_chunks if c_id in chunk_map]
            
            # Select components using policy
            from presentation_engine.component_policy import build_components
            components = build_components(target_spec.section_id, section_chunks)
            
            sections.append(Section(
                section_id=target_spec.section_id,
                kind=target_spec.section_type,
                components=components
            ))
            
        return Document(
            topic=ia_schema.topic,
            workspace_type=ia_schema.workspace_type,
            sections=sections,
            ia_schema=ia_schema
        )
