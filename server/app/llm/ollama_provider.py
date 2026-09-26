from ollama import AsyncClient
from pydantic import ValidationError

from app.config import settings
from app.llm.base import LLMProvider, SchemaT


class OllamaProvider(LLMProvider):
    def __init__(self, model: str, *, num_thread: int = 4, keep_alive: str = "2m", num_ctx: int = 8192):
        self._model = model
        self._keep_alive = keep_alive
        # num_gpu=0 keeps every layer on the CPU so classification never takes
        # VRAM away from whatever else is running (games, notes_app's models).
        # num_thread caps the CPU cost of a batch; temperature 0 because this
        # is a judgement call we want to be repeatable, not creative.
        self._options = {"num_gpu": 0, "num_thread": num_thread, "num_ctx": num_ctx, "temperature": 0}
        self._client = AsyncClient(host=settings.ollama_base_url)

    def model_name(self) -> str:
        return self._model

    async def structured_extract(self, system: str, prompt: str, schema: type[SchemaT]) -> SchemaT:
        # Passing the JSON schema itself as `format` (rather than the literal
        # "json") makes Ollama constrain decoding via grammar -- small local
        # models otherwise tend to echo a schema described in text back
        # verbatim (learned the hard way in notes_app).
        schema_json = schema.model_json_schema()

        last_error: str | None = None
        for attempt in range(2):
            instructions = prompt if attempt == 0 else f"{prompt}\n\n(Previous attempt was invalid: {last_error})"
            response = await self._client.chat(
                model=self._model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": instructions}],
                format=schema_json,
                stream=False,
                options=self._options,
                keep_alive=self._keep_alive,
            )
            raw = response["message"]["content"]
            try:
                return schema.model_validate_json(raw)
            except ValidationError as exc:
                last_error = str(exc)

        raise ValueError(f"Ollama structured_extract failed validation after retries: {last_error}")
