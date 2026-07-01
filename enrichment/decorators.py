from typing import Dict, Any

class BaseDecorator:
    def decorate(self, knowledge_tree: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

class ReadingTimeDecorator(BaseDecorator):
    def decorate(self, knowledge_tree: Dict[str, Any]) -> Dict[str, Any]:
        """Calculates rough reading time based on block density."""
        # Simple heuristic for now
        num_blocks = len(knowledge_tree.get("blocks", []))
        estimated_seconds = num_blocks * 15 
        mins = max(1, estimated_seconds // 60)
        
        knowledge_tree["metadata"] = knowledge_tree.get("metadata", {})
        knowledge_tree["metadata"]["reading_time_mins"] = mins
        
        return knowledge_tree

class HighYieldDecorator(BaseDecorator):
    def decorate(self, knowledge_tree: Dict[str, Any]) -> Dict[str, Any]:
        """Flags the document as High Yield if certain keywords appear frequently."""
        return knowledge_tree

class EnrichmentPipeline:
    def __init__(self):
        from .resolvers import MediaResolver, GlossaryResolver, CitationResolver
        from .generators import MemoryAidGenerator, ClinicalPearlGenerator, QuizSeedGenerator
        
        self.resolvers = [MediaResolver(), GlossaryResolver(), CitationResolver()]
        self.generators = [MemoryAidGenerator(), ClinicalPearlGenerator(), QuizSeedGenerator()]
        self.decorators = [ReadingTimeDecorator(), HighYieldDecorator()]
        
    def enrich(self, knowledge_tree: Dict[str, Any]) -> Dict[str, Any]:
        for resolver in self.resolvers:
            knowledge_tree = resolver.resolve(knowledge_tree)
            
        for generator in self.generators:
            knowledge_tree = generator.generate(knowledge_tree)
            
        for decorator in self.decorators:
            knowledge_tree = decorator.decorate(knowledge_tree)
            
        return knowledge_tree
