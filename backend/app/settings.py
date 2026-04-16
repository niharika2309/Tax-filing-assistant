from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    lm_studio_base_url: str = "http://localhost:1234/v1"
    lm_studio_api_key: str = "lm-studio"
    model_name: str = "qwen2.5-7b-instruct"
    model_temperature: float = 0.1

    storage_dir: Path = Path("storage")
    checkpoints_db: Path = Path("storage/checkpoints.db")
    app_db: Path = Path("storage/app.db")

    tool_retry_budget: int = 3
    tax_year: int = 2025


settings = Settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)
