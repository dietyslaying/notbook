from interfaces import Document, WorkspaceSession, IIAGenerator, IPresentationEngine, KnowledgeTree

class DiseaseWorkspace:
    def __init__(self, ia_generator: IIAGenerator, presentation_engine: IPresentationEngine):
        self.ia = ia_generator
        self.pe = presentation_engine

    def generate_screen(self, session: WorkspaceSession, screen_id: str) -> Document:
        # If knowledge tree is missing, initialize an empty one for now
        if not session.knowledge_tree:
            session.knowledge_tree = KnowledgeTree(
                topic=session.topic,
                workspace_type=session.workspace_type,
                chunks=[]
            )
            
        # If IA schema is missing, generate it
        if not session.ia_schema:
            session.ia_schema = self.ia.generate(
                session.knowledge_tree,
                session.workspace_type,
                session.user_mode
            )
            
        return self.pe.generate_document(session.ia_schema, session.knowledge_tree, screen_id)
