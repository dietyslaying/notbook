"""Google Gen AI SDK client (google.genai) — replaces deprecated google.generativeai."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Optional

from google import genai
from google.genai import types

from config import config

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self) -> None:
        llm = config.raw_config.get("llm") or {}
        self.model_name = str(llm.get("model_name") or "gemini-3.5-flash")
        self.temperature = float(llm.get("temperature", 0.15))
        self.top_p = float(llm.get("top_p", 0.9))
        self.top_k = int(llm.get("top_k", 32))
        self.max_output_tokens = int(llm.get("max_output_tokens", 4096))
        self._lock = asyncio.Lock()
        self._clients: dict[str, genai.Client] = {}

    def _client_for(self, api_key: str) -> genai.Client:
        if api_key not in self._clients:
            self._clients[api_key] = genai.Client(api_key=api_key)
        return self._clients[api_key]

    def _pick_key(self) -> str:
        keys = config.gemini_api_keys
        if not keys:
            raise RuntimeError("No Gemini API keys configured")
        return random.choice(keys)

    def _gen_config(self, *, json_mode: bool = True) -> types.GenerateContentConfig:
        kwargs: dict = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "max_output_tokens": self.max_output_tokens,
        }
        if json_mode:
            kwargs["response_mime_type"] = "application/json"
        return types.GenerateContentConfig(**kwargs)

    async def generate(
        self,
        prompt: str,
        *,
        json_mode: bool = True,
        model: Optional[str] = None,
    ) -> str:
        api_key = self._pick_key()
        client = self._client_for(api_key)
        model_name = model or self.model_name
        cfg = self._gen_config(json_mode=json_mode)

        def _call() -> str:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=cfg,
            )
            text = getattr(response, "text", None) or ""
            if text:
                return text
            # Fallback walk candidates
            try:
                cands = response.candidates or []
                if cands and cands[0].content and cands[0].content.parts:
                    return cands[0].content.parts[0].text or ""
            except Exception:
                pass
            return ""

        async with self._lock:
            return await asyncio.to_thread(_call)


gemini_client = GeminiClient()
