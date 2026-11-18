"""A tiny, provider-agnostic LLM client.

The demo does not depend on one vendor. Any server that speaks the OpenAI
chat-completions format works: Groq, OpenRouter, Google Gemini (OpenAI endpoint),
a local Ollama, OpenAI itself. Standard library only, so the demo has no runtime
dependencies.

With no provider configured the demo still runs: `get_llm()` returns None and
every feature falls back to its deterministic, template-based path.

Configuration (environment variables):

    LLM_PROVIDER   groq | openrouter | gemini | ollama | openai | custom | off
    LLM_API_KEY    key for the provider (not needed for ollama)
    LLM_MODEL      override the provider's default model
    LLM_VISION_MODEL  model used for reading boarding-pass photos
    LLM_BASE_URL   only for LLM_PROVIDER=custom
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import urllib.error
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

# Small, cheap models that are good enough for a demo.
PRESETS: dict[str, dict[str, str]] = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-20b",
        "vision_model": "qwen/qwen3.8-27b",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.1-8b-instruct",
        "vision_model": "google/gemini-2.0-flash-001",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash-lite",
        "vision_model": "gemini-2.0-flash-lite",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.2:3b",
        "vision_model": "llama3.2-vision",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "vision_model": "gpt-4o-mini",
    },
}


class LLMError(RuntimeError):
    pass


@dataclass
class LLM:
    base_url: str
    model: str
    api_key: str = ""
    vision_model: str = ""
    timeout: float = 30.0
    # Same request, same answer: repeat questions (sample buttons, re-runs) cost
    # no tokens and come back instantly. 0 turns the cache off.
    cache_size: int = 256
    _cache: OrderedDict[str, str] = field(default_factory=OrderedDict, repr=False, compare=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    hits: int = field(default=0, repr=False, compare=False)

    @property
    def label(self) -> str:
        return self.model

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 600,
        model: str | None = None,
        json_mode: bool = False,
    ) -> str:
        body: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if body["model"].startswith("openai/gpt-oss"):
            # Reasoning model: keep thinking short, and leave room for it in the budget.
            body["reasoning_effort"] = "low"
            body["max_tokens"] = max(max_tokens, 1000)
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        if self.cache_size:
            with self._lock:
                if key in self._cache:
                    self._cache.move_to_end(key)
                    self.hits += 1
                    return self._cache[key]
        text = self._post(body, messages, temperature=temperature, max_tokens=max_tokens, model=model,
                          json_mode=json_mode)
        if self.cache_size and text.strip():
            with self._lock:
                self._cache[key] = text
                while len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
        return text

    def _post(self, body: dict[str, Any], messages: list[dict[str, Any]], *, temperature: float,
              max_tokens: int, model: str | None, json_mode: bool) -> str:
        req = urllib.request.Request(
            self.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                # Groq sits behind Cloudflare, which rejects urllib's default
                # "Python-urllib" agent with HTTP 403 (error 1010).
                "User-Agent": "flyclaim-demo/1.0",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if json_mode and e.code == 400 and "response_format" in detail:
                # Some models reject JSON mode; retry with the instruction alone.
                return self.chat(messages, temperature=temperature, max_tokens=max_tokens, model=model)
            raise LLMError(f"LLM HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise LLMError(f"LLM unreachable: {e}") from e
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"Unexpected LLM response: {str(data)[:300]}") from e

    def chat_json(self, messages: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
        """Ask for JSON and parse it, tolerating code fences and chatter around it."""
        return parse_json(self.chat(messages, json_mode=True, **kw))


def parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise LLMError(f"No JSON in LLM output: {text[:200]}") from None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise LLMError(f"Bad JSON in LLM output: {text[:200]}") from e


def get_llm(env: dict[str, str] | None = None) -> LLM | None:
    """Build the client from the environment, or None for offline mode."""
    env = dict(os.environ if env is None else env)
    provider = env.get("LLM_PROVIDER", "").strip().lower()
    key = env.get("LLM_API_KEY", "").strip()

    if provider in {"off", "none", "mock"}:
        return None
    if not provider:
        if not key:
            return None
        provider = "groq"  # a key on its own means the default free-tier provider

    if provider == "custom":
        base_url = env.get("LLM_BASE_URL", "").strip()
        model = env.get("LLM_MODEL", "").strip()
        if not base_url or not model:
            raise LLMError("LLM_PROVIDER=custom needs LLM_BASE_URL and LLM_MODEL")
        preset = {"base_url": base_url, "model": model, "vision_model": model}
    elif provider in PRESETS:
        preset = PRESETS[provider]
    else:
        raise LLMError(f"Unknown LLM_PROVIDER {provider!r}; use one of {', '.join(PRESETS)}, custom, off")

    if provider != "ollama" and provider != "custom" and not key:
        raise LLMError(f"LLM_PROVIDER={provider} needs LLM_API_KEY")

    return LLM(
        base_url=env.get("LLM_BASE_URL", preset["base_url"]).strip(),
        model=env.get("LLM_MODEL", preset["model"]).strip(),
        api_key=key,
        vision_model=env.get("LLM_VISION_MODEL", preset["vision_model"]).strip(),
    )
