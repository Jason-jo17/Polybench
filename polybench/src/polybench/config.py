from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# The polybench/ project directory (holds sandbox/, tasks/ and pyproject.toml).
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Cloud LLM providers
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    together_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    xai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    fireworks_api_key: Optional[str] = None
    perplexity_api_key: Optional[str] = None

    # Local provider endpoints
    ollama_base_url: str = "http://localhost:11434/v1"
    lmstudio_base_url: str = "http://localhost:1234/v1"

    # PolyBench settings
    polybench_db: str = "./polybench.db"
    polybench_default_model: str = "claude-sonnet-4-6"
    polybench_dashboard_password: Optional[str] = None
    polybench_max_concurrent_runs: int = 1
    polybench_tasks_dir: str = "./tasks"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
