import asyncio
from typing import AsyncGenerator, Any

class StreamingPipeline:
    """
    Manages the flow from Gemini stream -> Semantic AST -> Layout Engine -> Renderer -> Delivery.
    """
    def __init__(self, backend_renderer):
        self.backend = backend_renderer
        
    async def process_stream(self, raw_gemini_stream) -> AsyncGenerator[str, None]:
        """
        Coordinates the real-time parsing and streaming by maintaining a Semantic Boundary Buffer.
        Instead of yielding arbitrary chunks, it only yields completely formed Component layouts.
        """
        from partial_json_parser import parse_partial_json
        from knowledge_validator import KnowledgeValidator
        from enrichment.decorators import EnrichmentPipeline
        from content_intelligence import ContentIntelligence
        from layout.layout_engine import LayoutEngine
        import asyncio

        validator = KnowledgeValidator()
        enricher = EnrichmentPipeline()
        intelligence = ContentIntelligence()
        layout_engine = LayoutEngine()
        
        full_buffer = ""
        last_component_count = 0
        last_html_state = ""
        
        async for chunk_text, chunk_complete in raw_gemini_stream:
            if chunk_text is None:
                continue
            full_buffer += str(chunk_text)
            
            # Attempt to parse what we have so far
            try:
                partial_ast = parse_partial_json(full_buffer)
                valid_tree = validator.validate(partial_ast)
                enriched_tree = enricher.enrich(valid_tree)
                component_tree = layout_engine.process(enriched_tree)
                
                # Check if we crossed a semantic boundary (a new component was added)
                current_count = len(component_tree)
                
                if current_count > last_component_count or chunk_complete:
                    # Rerender the whole tree (since partials might have updated)
                    # In a highly optimized incremental renderer, we'd only render the diff
                    rendered_html = ""
                    for comp in component_tree:
                        c_type = getattr(comp, "type", "")
                        if c_type == "heading":
                            rendered_html += f"<b>{getattr(comp, 'icon', '')} {getattr(comp, 'text', '')}</b>\n\n"
                        elif c_type == "paragraph":
                            rendered_html += f"{getattr(comp, 'text', '')}\n\n"
                        elif c_type == "checklist":
                            rendered_html += "".join([f"• {item}\n" for item in getattr(comp, "items", [])]) + "\n"
                        elif c_type == "table":
                            rendered_html += f"<b>{comp.headers[0] if comp.headers else 'Table'}</b>\n"
                            for row in comp.rows:
                                rendered_html += f"• {row[0]}: {row[1]} vs {row[2]}\n"
                            rendered_html += "\n"
                        elif c_type == "divider":
                            rendered_html += "──────────\n\n"
                            
                    if rendered_html != last_html_state:
                        last_html_state = rendered_html
                        last_component_count = current_count
                        yield rendered_html
                        
            except Exception as e:
                # If parsing fails mid-stream, just buffer more chunks
                continue
