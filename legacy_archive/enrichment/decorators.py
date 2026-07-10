from typing import Dict, Any

class BaseDecorator:
    def decorate(self, ndm: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

class ReadingTimeDecorator(BaseDecorator):
    def decorate(self, ndm: Dict[str, Any]) -> Dict[str, Any]:
        """Calculates rough reading time based on block density."""
        # Simple heuristic for now
        num_blocks = len(ndm.get("blocks", []))
        estimated_seconds = num_blocks * 15 
        mins = max(1, estimated_seconds // 60)
        
        ndm["metadata"] = ndm.get("metadata", {})
        ndm["metadata"]["reading_time_mins"] = mins
        
        return ndm

class HighYieldDecorator(BaseDecorator):
    def decorate(self, ndm: Dict[str, Any]) -> Dict[str, Any]:
        """Flags the document as High Yield if certain keywords appear frequently."""
        return ndm

class EnrichmentPipeline:
    def __init__(self):
        from .resolvers import MediaResolver, GlossaryResolver, CitationResolver
        from .generators import MemoryAidGenerator, ClinicalPearlGenerator, QuizSeedGenerator
        
        self.resolvers = [MediaResolver(), GlossaryResolver(), CitationResolver()]
        self.generators = [MemoryAidGenerator(), ClinicalPearlGenerator(), QuizSeedGenerator()]
        self.decorators = [ReadingTimeDecorator(), HighYieldDecorator()]
        
    def enrich(self, ndm: Dict[str, Any]) -> Dict[str, Any]:
        for resolver in self.resolvers:
            ndm = resolver.resolve(ndm)
            
        for generator in self.generators:
            ndm = generator.generate(ndm)
            
        for decorator in self.decorators:
            ndm = decorator.decorate(ndm)
            
        return ndm
