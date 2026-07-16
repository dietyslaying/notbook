"""Google Gen AI SDK client (google.genai) — rotates keys on 429/quota."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from google.genai import types

from config import config
from services.gemini_key_pool import gemini_key_pool, is_quota_or_rate

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
        model_name = model or self.model_name
        cfg = self._gen_config(json_mode=json_mode)
        n_keys = max(1, gemini_key_pool.key_count())
        attempts = max(4, n_keys * 2)
        last_err: Exception | None = None

        async with self._lock:
            for attempt in range(attempts):
                api_key, client = gemini_key_pool.acquire()

                def _call() -> str:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=cfg,
                    )
                    text = getattr(response, "text", None) or ""
                    if text:
                        return text
                    try:
                        cands = response.candidates or []
                        if cands and cands[0].content and cands[0].content.parts:
                            return cands[0].content.parts[0].text or ""
                    except Exception:
                        pass
                    return ""

                try:
                    text = await asyncio.to_thread(_call)
                    gemini_key_pool.mark_ok(api_key)
                    return text
                except Exception as e:
                    last_err = e
                    cool = gemini_key_pool.mark_error(api_key, e)
                    err = str(e)
                    if is_quota_or_rate(err):
                        logger.warning(
                            "generate 429/quota (attempt %s/%s); rotating keys "
                            "(cooldown %.0fs on failed key)",
                            attempt + 1,
                            attempts,
                            cool,
                        )
                        if n_keys <= 1:
                            await asyncio.sleep(min(cool, 15.0))
                        continue
                    if attempt + 1 >= attempts:
                        break
                    await asyncio.sleep(min(1.5 * (attempt + 1), 8.0))

        raise RuntimeError(
            f"Gemini generate failed after rotating keys: {last_err}"
        ) from last_err


gemini_client = GeminiClient()
