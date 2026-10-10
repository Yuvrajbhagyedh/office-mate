"""LLM client wrappers.

Supports:
  * google    — Gemini free tier (https://aistudio.google.com/apikey)
  * groq      — free-tier friendly (https://console.groq.com/keys)
  * xai       — Grok models (https://console.x.ai/)
  * anthropic — Claude (paid)
  * openai    — any OpenAI-compatible endpoint via LLM_BASE_URL + LLM_API_KEY

All providers expose `generate(system, user) -> str` so the rest of the
pipeline stays provider-agnostic.
"""
from __future__ import annotations

from typing import Optional

import httpx

from ..config import settings
from ..logging_config import get_logger

logger = get_logger(__name__)

_PLACEHOLDER_FRAGMENTS = ("REPLACE", "your-key-here", "YOUR_KEY", "xxx")


class LLMNotConfigured(Exception):
    pass


def _is_placeholder(key: Optional[str]) -> bool:
    if not key or not key.strip():
        return True
    upper = key.upper()
    return any(frag.upper() in upper for frag in _PLACEHOLDER_FRAGMENTS)


class GeminiLLM:
    """Google Gemini via the Generative Language REST API."""

    # Tried in order when the primary model is overloaded (503) or rate-limited.
    _FALLBACKS = (
        "gemini-flash-latest",
        "gemini-2.0-flash",
        "gemini-flash-lite-latest",
        "gemini-2.0-flash-lite",
        "gemini-3.5-flash",
    )

    def __init__(self, api_key: Optional[str], model: str, max_tokens: int):
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens

    @property
    def model(self) -> str:
        return self._model

    def _require_key(self) -> str:
        if _is_placeholder(self._api_key):
            raise LLMNotConfigured(
                "GOOGLE_API_KEY / GEMINI_API_KEY is missing or still a placeholder. "
                "Get a free key at https://aistudio.google.com/apikey and set it in backend/.env."
            )
        return self._api_key.strip()  # type: ignore[union-attr]

    def _model_candidates(self) -> list[str]:
        primary = self._model[len("models/") :] if self._model.startswith("models/") else self._model
        seen: set[str] = set()
        ordered: list[str] = []
        for name in (primary, *self._FALLBACKS):
            if name and name not in seen:
                seen.add(name)
                ordered.append(name)
        return ordered

    def generate(self, system: str, user: str) -> str:
        key = self._require_key()
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": self._max_tokens,
            },
        }
        last_err = "Google Gemini unavailable"
        with httpx.Client(timeout=120.0) as client:
            for model in self._model_candidates():
                url = (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent"
                )
                for attempt in range(3):
                    try:
                        resp = client.post(
                            url,
                            headers={
                                "Content-Type": "application/json",
                                "x-goog-api-key": key,
                            },
                            json=payload,
                        )
                    except httpx.HTTPError as exc:
                        last_err = f"Google Gemini request failed: {exc}"
                        continue

                    if resp.status_code in (401, 403):
                        raise LLMNotConfigured(
                            "Google rejected the API key (invalid, restricted, or expired). "
                            "Create a free key at https://aistudio.google.com/apikey and set "
                            "GOOGLE_API_KEY in backend/.env."
                        )
                    if resp.status_code in (429, 503):
                        last_err = f"Google Gemini error {resp.status_code}: {resp.text[:300]}"
                        logger.warning(
                            "Gemini overloaded; retrying",
                            extra={"extra": {"model": model, "attempt": attempt + 1}},
                        )
                        import time

                        time.sleep(1.5 * (attempt + 1))
                        continue
                    if resp.status_code >= 400:
                        last_err = f"Google Gemini error {resp.status_code}: {resp.text[:500]}"
                        break  # try next model

                    data = resp.json()
                    try:
                        parts = data["candidates"][0]["content"]["parts"]
                        text = "".join(p.get("text", "") for p in parts).strip()
                        if not text:
                            raise KeyError("empty text")
                        self._model = model
                        return text
                    except (KeyError, IndexError, TypeError) as exc:
                        last_err = f"Unexpected Google Gemini response: {data}"
                        raise RuntimeError(last_err) from exc

        raise RuntimeError(
            f"{last_err} Google is busy — wait a minute and try again."
        )


class OpenAICompatibleLLM:
    """Groq / xAI / any OpenAI-compatible chat completions API."""

    def __init__(
        self,
        api_key: Optional[str],
        model: str,
        max_tokens: int,
        base_url: str,
        provider_name: str,
        key_hint: str,
    ):
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._base_url = base_url.rstrip("/")
        self._provider_name = provider_name
        self._key_hint = key_hint

    @property
    def model(self) -> str:
        return self._model

    def _require_key(self) -> str:
        if _is_placeholder(self._api_key):
            raise LLMNotConfigured(
                f"{self._provider_name} API key is missing or still a placeholder. "
                f"{self._key_hint}"
            )
        return self._api_key.strip()  # type: ignore[union-attr]

    def generate(self, system: str, user: str) -> str:
        key = self._require_key()
        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self._max_tokens,
            "temperature": 0,
        }
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"{self._provider_name} request failed: {exc}") from exc

        if resp.status_code in (401, 403):
            raise LLMNotConfigured(
                f"{self._provider_name} rejected the API key (invalid or expired). "
                f"{self._key_hint}"
            )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"{self._provider_name} error {resp.status_code}: {resp.text[:500]}"
            )

        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise RuntimeError(f"Unexpected {self._provider_name} response: {data}") from exc


class AnthropicLLM:
    def __init__(self, api_key: Optional[str], model: str, max_tokens: int, effort: str):
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._effort = effort
        self._client = None

    @property
    def model(self) -> str:
        return self._model

    def _ensure_client(self):
        if _is_placeholder(self._api_key):
            raise LLMNotConfigured(
                "ANTHROPIC_API_KEY is missing or still a placeholder. "
                "Set a real key in backend/.env (starts with sk-ant-) and restart the backend."
            )
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._api_key.strip())
        return self._client

    def generate(self, system: str, user: str) -> str:
        client = self._ensure_client()
        import anthropic

        try:
            message = client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                extra_body={"output_config": {"effort": self._effort}},
            )
        except anthropic.AuthenticationError as exc:
            raise LLMNotConfigured(
                "Anthropic rejected ANTHROPIC_API_KEY (invalid or expired). "
                "Update backend/.env with a valid key and restart the backend."
            ) from exc
        return "".join(
            block.text for block in message.content if block.type == "text"
        ).strip()


def build_llm():
    provider = (settings.llm_provider or "google").strip().lower()

    if provider in {"google", "gemini"}:
        return GeminiLLM(
            api_key=settings.google_api_key or settings.gemini_api_key or settings.llm_api_key,
            model=settings.llm_model or "gemini-flash-latest",
            max_tokens=settings.llm_max_tokens,
        )

    if provider == "anthropic":
        return AnthropicLLM(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            effort=settings.llm_effort,
        )

    if provider == "xai":
        return OpenAICompatibleLLM(
            api_key=settings.xai_api_key or settings.llm_api_key,
            model=settings.llm_model or "grok-2-latest",
            max_tokens=settings.llm_max_tokens,
            base_url=settings.llm_base_url or "https://api.x.ai/v1",
            provider_name="xAI (Grok)",
            key_hint="Get a key at https://console.x.ai/ and set XAI_API_KEY in backend/.env.",
        )

    if provider in {"openai", "custom", "explabs"}:
        return OpenAICompatibleLLM(
            api_key=settings.llm_api_key,
            model=settings.llm_model or "gemini-flash-latest",
            max_tokens=settings.llm_max_tokens,
            base_url=settings.llm_base_url or "https://api.openai.com/v1",
            provider_name="OpenAI-compatible endpoint",
            key_hint="Set LLM_API_KEY and LLM_BASE_URL in backend/.env.",
        )

    if provider == "groq":
        return OpenAICompatibleLLM(
            api_key=settings.groq_api_key or settings.llm_api_key,
            model=settings.llm_model or "llama-3.3-70b-versatile",
            max_tokens=settings.llm_max_tokens,
            base_url=settings.llm_base_url or "https://api.groq.com/openai/v1",
            provider_name="Groq",
            key_hint="Get a free key at https://console.groq.com/keys and set GROQ_API_KEY in backend/.env.",
        )

    raise LLMNotConfigured(
        f"Unknown LLM_PROVIDER={provider!r}. "
        "Use google, groq, xai, anthropic, or openai (any OpenAI-compatible base URL)."
    )


llm = build_llm()
