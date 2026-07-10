from interfaces import Document, WorkspaceSession, IIAGenerator, IPresentationEngine, KnowledgeTree

class DiseaseWorkspace:
    def __init__(self, ia_generator: IIAGenerator, presentation_engine: IPresentationEngine):
        self.ia = ia_generator
        self.pe = presentation_engine

    async def generate_screen_stream(self, session: WorkspaceSession, screen_id: str):
        import gemini_service
        from partial_json_parser import parse_partial_json
        
        # If knowledge tree is missing, initialize an empty one
        if not session.knowledge_tree:
            session.knowledge_tree = KnowledgeTree(
                topic=session.topic,
                workspace_type=session.workspace_type,
                chunks=[]
            )
            
        namespace = session.metadata.get("namespace", "global|murtaghs")
        
        full_json = ""
        last_block_count = 0
        
        # We start the RAG stream
        stream = gemini_service.query_rag_stream(namespace=namespace, user_question=session.topic)
        
        async for text_chunk, is_complete in stream:
            if not text_chunk:
                continue
                
            full_json += str(text_chunk)
            
            try:
                parsed = parse_partial_json(full_json)
                # Validate semantic blocks with NDMValidator
                from ndm_validator import NDMValidator
                parsed = NDMValidator().validate(parsed)
                blocks = parsed.get("blocks", [])
                
                # Check if a new block was added or if it's the final chunk
                if len(blocks) > last_block_count or is_complete:
                    last_block_count = len(blocks)
                    
                    # Convert blocks to Chunk objects
                    from interfaces import Chunk
                    new_chunks = []
                    
                    if not blocks and is_complete and full_json.strip() and not full_json.strip().startswith("{"):
                        # Handle raw text fallback (like Pinecone "not found" error messages)
                        new_chunks.append(Chunk(
                            chunk_id="overview_0",
                            chunk_type="overview",
                            text=full_json.strip(),
                            textbook=namespace,
                            retrieval_score=1.0
                        ))
                    else:
                        for idx, b in enumerate(blocks):
                            # Extract the type as chunk_type, or fallback to something generic
                            c_type = b.get("type", "unknown") if isinstance(b, dict) else "unknown"
                            
                            if isinstance(b, dict):
                                new_chunks.append(Chunk(
                                    chunk_id=f"{c_type}_{idx}",
                                    chunk_type=c_type,
                                    payload=b,
                                    text="",
                                    textbook=namespace,
                                    retrieval_score=1.0
                                ))
                            else:
                                new_chunks.append(Chunk(
                                    chunk_id=f"text_{idx}",
                                    chunk_type="text",
                                    payload={},
                                    text=str(b),
                                    textbook=namespace,
                                    retrieval_score=1.0
                                ))
                        
                    session.knowledge_tree.chunks = new_chunks
                    
                    # Regenerate IA Schema with new chunks
                    session.ia_schema = self.ia.generate(
                        session.knowledge_tree,
                        session.workspace_type,
                        session.user_mode
                    )
                    
                    doc = self.pe.generate_document(session.ia_schema, session.knowledge_tree, screen_id)
                    yield doc
            except Exception as e:
                # If partial parsing fails, just continue collecting chunks
                continue
                
        # If nothing was yielded (e.g. streaming failed completely) or just as a fallback
        if not session.ia_schema:
            session.ia_schema = self.ia.generate(
                session.knowledge_tree,
                session.workspace_type,
                session.user_mode
            )
            doc = self.pe.generate_document(session.ia_schema, session.knowledge_tree, screen_id)
            yield doc
            
    def generate_screen(self, session: WorkspaceSession, screen_id: str) -> Document:
        # Legacy synchronous fallback
        if not session.knowledge_tree:
            session.knowledge_tree = KnowledgeTree(
                topic=session.topic,
                workspace_type=session.workspace_type,
                chunks=[]
            )
        if not session.ia_schema:
            session.ia_schema = self.ia.generate(session.knowledge_tree, session.workspace_type, session.user_mode)
        return self.pe.generate_document(session.ia_schema, session.knowledge_tree, screen_id)
