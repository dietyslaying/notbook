import pytest
from interfaces import (
    IQuizEngine,
    KnowledgeTree,
    Chunk,
    Difficulty,
    AnswerPosition,
    WorkspaceType
)
from quiz_engine.generator import QuizEngine

class TestQuizEngineContract:
    @pytest.fixture
    def engine(self) -> IQuizEngine:
        return QuizEngine()

    def test_quiz_answer_randomization(self, engine: IQuizEngine):
        chunks = [
            Chunk(chunk_id=f"c{i}", text=f"Fact {i}", textbook="Book", retrieval_score=0.9)
            for i in range(10)
        ]
        kt = KnowledgeTree(topic="Disease", workspace_type=WorkspaceType.DISEASE, chunks=chunks)
        
        # Ask for 100 questions to verify distribution
        # Note: the PRD says 100 questions generated, check distribution.
        # Since generating 100 questions with dummy chunks might reuse them, we pass enough chunks or let it repeat.
        session = engine.generate(kt, Difficulty.EASY, 100)
        
        counts = {AnswerPosition.A: 0, AnswerPosition.B: 0, AnswerPosition.C: 0, AnswerPosition.D: 0}
        
        for q in session.questions:
            assert len(q.options) == 4
            counts[q.correct_position] += 1
            
            # Verify the option at the correct position has is_correct = True
            correct_opt = next(o for o in q.options if o.position == q.correct_position)
            assert correct_opt.is_correct is True
            
        # Check uniform distribution (roughly)
        for pos, count in counts.items():
            assert 10 <= count <= 40, f"Distribution skewed for {pos}: {count}"

    def test_evaluate_answer(self, engine: IQuizEngine):
        chunks = [Chunk(chunk_id="c1", text="Fact 1", textbook="Book", retrieval_score=0.9)]
        kt = KnowledgeTree(topic="Disease", workspace_type=WorkspaceType.DISEASE, chunks=chunks)
        session = engine.generate(kt, Difficulty.EASY, 1)
        
        q = session.questions[0]
        # Test correct answer
        is_correct, question = engine.evaluate(session, q.question_id, q.correct_position)
        assert is_correct is True
        assert session.score == 1
        assert session.answers[q.question_id] == q.correct_position
