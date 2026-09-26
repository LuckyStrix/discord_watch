from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://watch:watch@localhost:5432/discord_watch"
    ollama_base_url: str = "http://host.docker.internal:11434"
    discord_token: str | None = None


settings = Settings()
