from abc import ABC, abstractmethod
from typing import Generator

from rag_app.config import settings


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, system: str, max_tokens: int = 2000, temperature: float = 0) -> str:
        ...

    @abstractmethod
    def generate_stream(self, prompt: str, system: str, max_tokens: int = 2000, temperature: float = 0) -> Generator[str, None, None]:
        ...


class GeminiProvider(LLMProvider):
    def __init__(self):
        from google import genai
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._model = settings.GEMINI_MODEL

    def generate(self, prompt: str, system: str, max_tokens: int = 2000, temperature: float = 0) -> str:
        from google.genai import types
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        return response.text.strip()

    def generate_stream(self, prompt: str, system: str, max_tokens: int = 2000, temperature: float = 0) -> Generator[str, None, None]:
        from google.genai import types
        response = self._client.models.generate_content_stream(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        for chunk in response:
            if chunk.text:
                yield chunk.text


class OpenAIProvider(LLMProvider):
    def __init__(self):
        from openai import OpenAI
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = settings.OPENAI_GENERATION_MODEL

    def generate(self, prompt: str, system: str, max_tokens: int = 2000, temperature: float = 0) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()

    def generate_stream(self, prompt: str, system: str, max_tokens: int = 2000, temperature: float = 0) -> Generator[str, None, None]:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content


_PROVIDERS = {
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
}


def create_llm_provider() -> LLMProvider:
    provider_name = settings.LLM_PROVIDER.lower()
    cls = _PROVIDERS.get(provider_name)
    if cls is None:
        raise ValueError(f"Unknown LLM_PROVIDER '{provider_name}'. Choose from: {list(_PROVIDERS.keys())}")
    return cls()
