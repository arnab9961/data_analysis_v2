from pydantic import BaseSettings

class Settings(BaseSettings):
    API_KEY: str
    DATABASE_URL: str
    ALLOWED_ORIGINS: list[str]

    class Config:
        env_file = ".env"

settings = Settings()