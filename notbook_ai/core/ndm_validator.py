import json
from interfaces import NDMDocument
from pydantic import ValidationError

class NDMValidator:
    @staticmethod
    def validate(raw_llm_output: str) -> dict:
        try:
            data = json.loads(raw_llm_output)
            # Validate against our strict Pydantic model
            doc = NDMDocument(**data)
            return doc.model_dump()
        except json.JSONDecodeError:
            # If LLM forgot JSON formatting, fail fast
            return {"error": "LLM did not return valid JSON."}
        except ValidationError as e:
            # If LLM missed a field (e.g., core_facts), fail fast
            return {"error": f"NDM Validation failed: {str(e)}"}
        except Exception as e:
            return {"error": f"Unknown validation error: {str(e)}"}
