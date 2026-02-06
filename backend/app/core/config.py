from functools import lru_cache
from typing import List, Union

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables.
    """

    # General
    PROJECT_NAME: str = "AI Powered Interview Guide API"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "local"

    # CORS
    # In production, set this to a list of allowed origins, e.g.
    # ["https://your-frontend.com"]
    BACKEND_CORS_ORIGINS: List[Union[AnyHttpUrl, str]] = []

    # Database
    DATABASE_URL: str = "sqlite:///./app.db"

    # Security / Auth
    SECRET_KEY: str = "CHANGE_ME_SUPER_SECRET_KEY"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    ALGORITHM: str = "HS256"

    # File uploads / resumes
    RESUME_UPLOAD_DIR: str = "uploads/resumes"
    RESUME_MAX_SIZE_MB: int = 10

    # Gemini / ATS scoring
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "models/gemini-1.5-pro"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    Cached settings instance so we only load env once.
    """
    return Settings()


settings = get_settings()

