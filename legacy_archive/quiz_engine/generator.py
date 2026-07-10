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
        import asyncio
        from gemini_service import generate_quiz_questions
        
        context_text = ""
        for c in knowledge_tree.chunks:
            if c.text:
                context_text += f"{c.text}\n"
            else:
                context_text += f"{str(c.payload)}\n"
                
        if not context_text.strip():
            context_text = "General medical knowledge."
            
        generated = asyncio.run(generate_quiz_questions(context_text, count))
        
        questions = []
        for i, gq in enumerate(generated):
            options = []
            for opt in gq.get("options", []):
                # Ensure the correct AnswerPosition enum is used
                try:
                    pos = AnswerPosition(opt.get("position", "A"))
                except ValueError:
                    pos = AnswerPosition.A
                    
                options.append(QuizOption(
                    position=pos,
                    text=opt.get("text", ""),
                    is_correct=opt.get("is_correct", False)
                ))
            
            try:
                correct_pos = AnswerPosition(gq.get("correct_position", "A"))
            except ValueError:
                correct_pos = AnswerPosition.A
                
            q = QuizQuestion(
                question_id=str(uuid.uuid4()),
                question_text=gq.get("question_text", f"Sample Question {i}"),
                options=options,
                correct_position=correct_pos,
                explanation=gq.get("explanation", ""),
                source_chunk_id=knowledge_tree.chunks[0].chunk_id if knowledge_tree.chunks else "c1",
            )
            questions.append(q)
            
        # Fallback if generation fails
        if not questions:
            for i in range(count):
                options = [
                    QuizOption(position=AnswerPosition.A, text="Option A", is_correct=True),
                    QuizOption(position=AnswerPosition.B, text="Option B", is_correct=False),
                    QuizOption(position=AnswerPosition.C, text="Option C", is_correct=False),
                    QuizOption(position=AnswerPosition.D, text="Option D", is_correct=False),
                ]
                q = QuizQuestion(
                    question_id=str(uuid.uuid4()),
                    question_text=f"Sample Question {i}",
                    options=options,
                    correct_position=AnswerPosition.A,
                    explanation="This is a fallback explanation.",
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
