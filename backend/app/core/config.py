from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = Field(default="Meta Agent Backend", alias="APP_NAME")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    environment: str = Field(default="local", alias="ENVIRONMENT")
    google_search_api_key: str | None = Field(default=None, alias="GOOGLE_SEARCH_API_KEY")
    google_search_cx: str | None = Field(default=None, alias="GOOGLE_SEARCH_CX")
    amap_api_key: str | None = Field(default=None, alias="AMAP_API_KEY")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
