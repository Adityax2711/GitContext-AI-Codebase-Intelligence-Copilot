"""LLM abstraction layer supporting multiple configurable providers."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Protocol

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


class GitContextError(Exception):
    """Base exception for GitContext."""


class LLMError(GitContextError):
    """Base exception for LLM operations."""


class MissingAPIKeyError(LLMError):
    """Raised when an API key is required but not provided in environment."""


class LLMConfigurationError(LLMError):
    """Raised when LLM provider configuration is invalid or unsupported."""


class LLMClient(Protocol):
    """Protocol for LLM client implementations."""

    provider_name: str
    model_name: str

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text completion for given prompt and system instructions."""
        ...


class MockLLMClient:
    """Mock LLM client for testing and offline development."""

    def __init__(
        self,
        canned_response: Optional[str] = None,
        response_fn: Optional[Callable[[str, Optional[str]], str]] = None,
        model: str = "mock-model",
    ) -> None:
        self.provider_name = "mock"
        self.model_name = model
        self.canned_response = canned_response or "Insufficient evidence: Mock response."
        self.response_fn = response_fn
        self.call_history: List[Dict[str, Any]] = []

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        self.call_history.append({"prompt": prompt, "system_prompt": system_prompt})
        if self.response_fn:
            return self.response_fn(prompt, system_prompt)
        return self.canned_response


class OpenAILLMClient:
    """OpenAI and OpenAI-compatible API client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.0,
    ) -> None:
        self.provider_name = "openai"
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise MissingAPIKeyError(
                "OPENAI_API_KEY environment variable is missing. "
                "Please set OPENAI_API_KEY or configure a different provider in .env."
            )
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", str(temperature)))

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        url = f"{self.base_url}/chat/completions"
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return str(data["choices"][0]["message"]["content"]).strip()
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise LLMError(f"OpenAI API HTTP {e.code} error: {err_body}") from e
        except Exception as e:
            raise LLMError(f"OpenAI request failed: {e}") from e


class GeminiLLMClient:
    """Google Gemini API client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
    ) -> None:
        self.provider_name = "gemini"
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise MissingAPIKeyError(
                "GEMINI_API_KEY or GOOGLE_API_KEY environment variable is missing. "
                "Please set GEMINI_API_KEY or configure a different provider in .env."
            )
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-1.5-flash"
        self.temperature = float(os.getenv("LLM_TEMPERATURE", str(temperature)))

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        # Prefer google-generativeai package if installed and working
        try:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            gen_model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_prompt if system_prompt else None,
                generation_config={"temperature": self.temperature},
            )
            response = gen_model.generate_content(prompt)
            return response.text.strip()
        except ImportError:
            pass
        except Exception as e:
            # Fall back to REST API or raise
            raise LLMError(f"Gemini API request failed: {e}") from e

        # Direct REST API fallback
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_name}:generateContent?key={self.api_key}"
        )
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"System Instructions:\n{system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will strictly follow these instructions."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {"temperature": self.temperature},
        }
        headers = {"Content-Type": "application/json"}

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if not candidates:
                    return "Insufficient evidence: Model produced no response."
                return str(candidates[0]["content"]["parts"][0]["text"]).strip()
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise LLMError(f"Gemini API HTTP {e.code} error: {err_body}") from e
        except Exception as e:
            raise LLMError(f"Gemini request failed: {e}") from e


class AnthropicLLMClient:
    """Anthropic Claude API client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
    ) -> None:
        self.provider_name = "anthropic"
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise MissingAPIKeyError(
                "ANTHROPIC_API_KEY environment variable is missing. "
                "Please set ANTHROPIC_API_KEY or configure a different provider in .env."
            )
        self.model_name = model or os.getenv("LLM_MODEL") or "claude-3-5-sonnet-20241022"
        self.temperature = float(os.getenv("LLM_TEMPERATURE", str(temperature)))

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        url = "https://api.anthropic.com/v1/messages"
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": 1500,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content_blocks = data.get("content", [])
                text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
                return "\n".join(text_parts).strip()
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise LLMError(f"Anthropic API HTTP {e.code} error: {err_body}") from e
        except Exception as e:
            raise LLMError(f"Anthropic request failed: {e}") from e


class OllamaLLMClient:
    """Local Ollama client."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.provider_name = "ollama"
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
        self.model_name = model or os.getenv("LLM_MODEL") or "llama3"

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        url = f"{self.base_url}/api/chat"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return str(data["message"]["content"]).strip()
        except Exception as e:
            raise LLMError(f"Ollama local request failed: {e}") from e


def get_llm_client(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> LLMClient:
    """Factory creating an LLMClient instance based on configuration."""
    selected_provider = (provider or os.getenv("LLM_PROVIDER") or "").strip().lower()

    if not selected_provider:
        # Auto-detect provider if an API key is available
        if api_key:
            selected_provider = "openai"
        elif os.getenv("OPENAI_API_KEY"):
            selected_provider = "openai"
        elif os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            selected_provider = "gemini"
        elif os.getenv("ANTHROPIC_API_KEY"):
            selected_provider = "anthropic"
        else:
            # Default to openai which will raise a clean MissingAPIKeyError explaining how to configure
            selected_provider = "openai"

    if selected_provider == "openai":
        return OpenAILLMClient(api_key=api_key, model=model)
    elif selected_provider in ("gemini", "google"):
        return GeminiLLMClient(api_key=api_key, model=model)
    elif selected_provider == "anthropic":
        return AnthropicLLMClient(api_key=api_key, model=model)
    elif selected_provider == "ollama":
        return OllamaLLMClient(model=model)
    elif selected_provider == "mock":
        return MockLLMClient(model=model or "mock-model")
    else:
        raise LLMConfigurationError(
            f"Unsupported LLM provider '{selected_provider}'. "
            f"Supported providers: openai, gemini, anthropic, ollama, mock."
        )
