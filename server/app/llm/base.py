from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMProvider(ABC):
    """Provider-agnostic interface (same shape as notes_app's app.llm.base).
    Only structured extraction is needed here -- classification is a single
    schema-constrained call per batch, no streaming chat."""

    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    async def structured_extract(self, system: str, prompt: str, schema: type[SchemaT]) -> SchemaT:
        """Single-shot structured extraction, validated against `schema`."""
