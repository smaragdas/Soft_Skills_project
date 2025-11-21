from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')
    PROJECT_NAME: str = "softskills-bot"
    DATABASE_URL: str = "sqlite:///softskills.db"
    API_KEY: str = "supersecret123"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TEMPERATURE: float = 0.2
    OPENAI_BASE_URL: str | None = None

settings = Settings()
