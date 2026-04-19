"""LLM providers and (future) Pantheon agent classes.

Gen 1 ships only the LLMProvider protocol with two concrete
implementations: StubLLMProvider (always available) and
GeminiLLMProvider (lazy-loads the `gemini` extra on first call —
importing the class itself never touches google-genai).
OpenAILLMProvider and AnthropicLLMProvider live behind their
respective extras and land when a caller needs them.
"""

from theogony.agents.factory import build_llm_from_settings
from theogony.agents.llm import LLMProvider, LLMResult, StubLLMProvider
from theogony.agents.llm_gemini import GeminiLLMProvider

__all__ = [
    "GeminiLLMProvider",
    "LLMProvider",
    "LLMResult",
    "StubLLMProvider",
    "build_llm_from_settings",
]
