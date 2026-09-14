from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstract interface for LLM synthesis providers."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate response text from input prompt."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether provider and model are available."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return provider identifier (e.g. 'ollama')."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Return model identifier (e.g. 'llama3.2:3b')."""
        pass
