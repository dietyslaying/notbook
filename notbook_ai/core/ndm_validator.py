"""Validate and normalize LLM JSON into NDMDocument."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from interfaces import NDMDocument
from services.noise_filter import filter_ndm_dict


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


class NDMValidator:
    @staticmethod
    def _extract_json(raw: str) -> Any:
        text = (raw or "").strip()
        text = _FENCE.sub("", text).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try first {...} blob
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise

    @staticmethod
    def validate(raw_llm_output: str) -> dict:
        try:
            data = NDMValidator._extract_json(raw_llm_output)
            if not isinstance(data, dict):
                return {"error": "Model returned non-object JSON."}

            # Soft-fill missing optional lists
            data.setdefault("core_facts", [])
            data.setdefault("detail_sections", [])
            if not data.get("title"):
                data["title"] = "Topic"
            if not data.get("summary"):
                data["summary"] = "No summary available."
            if not data.get("source_citation"):
                data["source_citation"] = "Textbook excerpt"

            # Expandable → sections if model used old shape
            if not data.get("detail_sections") and data.get("expandable_details"):
                data["detail_sections"] = [
                    {"heading": "Details", "body": str(data["expandable_details"])}
                ]

            # Keep optional citation ids from model
            used = data.get("citations_used")

            # First pass pydantic (lenient via validators on model)
            doc = NDMDocument(**data)
            cleaned = filter_ndm_dict(doc.model_dump())
            if used is not None:
                cleaned["citations_used"] = used
            final = NDMDocument(**{k: v for k, v in cleaned.items() if k in NDMDocument.model_fields})
            out = final.model_dump()
            if used is not None:
                out["citations_used"] = used
            return out

        except json.JSONDecodeError:
            return {"error": "Could not parse a structured answer. Try rephrasing."}
        except ValidationError:
            # Last resort: noise-filter raw dict without full schema
            try:
                data = NDMValidator._extract_json(raw_llm_output)
                if isinstance(data, dict):
                    cleaned = filter_ndm_dict(data)
                    final = NDMDocument(**cleaned)
                    return final.model_dump()
            except Exception:
                pass
            return {"error": "Answer structure was incomplete. Try a shorter question."}
        except Exception:
            return {"error": "Something went wrong formatting the answer."}
