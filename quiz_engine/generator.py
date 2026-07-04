import random
import uuid
from interfaces import (
    IQuizEngine,
    KnowledgeTree,
    Difficulty,
    QuizSession,
    QuizQuestion,
    QuizOption,
    AnswerPosition
)

class QuizEngine(IQuizEngine):
    def generate(
        self,
        knowledge_tree: KnowledgeTree,
        difficulty: Difficulty,
        count: int,
    ) -> QuizSession:
        questions = []
        positions = [AnswerPosition.A, AnswerPosition.B, AnswerPosition.C, AnswerPosition.D]
        
        for i in range(count):
            # In a real implementation, we would extract a specific fact from a chunk to form a question
            # For this test-passing stub, we'll just generate dummy questions
            correct_pos = random.choice(positions)
            
            options = []
            for p in positions:
                is_correct = (p == correct_pos)
                options.append(QuizOption(
                    position=p,
                    text=f"Correct Answer for {i}" if is_correct else f"Distractor {p.name}",
                    is_correct=is_correct
                ))
                
            q = QuizQuestion(
                question_id=str(uuid.uuid4()),
                question_text=f"Sample Question {i}",
                options=options,
                correct_position=correct_pos,
                explanation="This is the explanation.",
                source_chunk_id="c1" if not knowledge_tree.chunks else knowledge_tree.chunks[0].chunk_id,
            )
            questions.append(q)
            
        return QuizSession(
            quiz_id=str(uuid.uuid4()),
            topic=knowledge_tree.topic,
            difficulty=difficulty,
            questions=questions
        )

    def evaluate(
        self,
        quiz_session: QuizSession,
        question_id: str,
        chosen: AnswerPosition,
    ) -> tuple[bool, QuizQuestion]:
        
        # Find the question
        question = next(q for q in quiz_session.questions if q.question_id == question_id)
        
        is_correct = (question.correct_position == chosen)
        
        # Record answer
        quiz_session.answers[question_id] = chosen
        if is_correct:
            quiz_session.score += 1
            
        return is_correct, question
