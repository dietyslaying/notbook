from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel
from layout.components import Document, RenderEvent, BaseComponent
from engine.interaction_engine import InteractionEngine, InteractionTree

class RenderInstruction(BaseModel):
    version: str = "1.0"
    event: RenderEvent
    component_id: str
    data: Optional[Dict[str, Any]] = None

class StreamingPlan(BaseModel):
    version: str = "1.0"
    instructions: List[RenderInstruction] = []

class RenderPlanner:
    """
    Decides the rendering sequence (StreamingPlan) and what interactions are available.
    """
    
    def __init__(self, interaction_engine: InteractionEngine):
        self.interaction_engine = interaction_engine
        
    def plan(self, doc: Document) -> Tuple[StreamingPlan, InteractionTree]:
        """
        Takes the static Component Tree (Document) and turns it into a timeline of RenderEvents
        and an InteractionTree of available actions.
        """
        
        instructions = []
        
        # Simplistic streaming plan for now: ADD everything sequentially.
        # Future enhancement: Stream high priority items first, lazily load low priority.
        for section in doc.sections:
            if section.state.visible:
                instructions.append(RenderInstruction(
                    event=RenderEvent.ADD,
                    component_id=section.component_id,
                    data={"kind": section.kind, "collapsed": section.state.collapsed}
                ))
                
                for comp in section.components:
                    if comp.state.visible:
                        instructions.append(RenderInstruction(
                            event=RenderEvent.ADD,
                            component_id=comp.component_id,
                            data={"type": comp.type, "payload": comp.dict()}
                        ))
        
        instructions.append(RenderInstruction(
            event=RenderEvent.STREAM_COMPLETE,
            component_id=doc.document_id
        ))
        
        streaming_plan = StreamingPlan(instructions=instructions)
        interaction_tree = self.interaction_engine.generate_interactions(doc)
        
        return streaming_plan, interaction_tree
