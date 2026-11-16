# school_bus_management/app/core/config.py
import os
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    PROJECT_NAME: str = "EDURIDE School Bus Management"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/school_bus_db")
    
    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days
    
    # Frontend
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    
    # Email
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", 587))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    FROM_EMAIL: str = os.getenv("FROM_EMAIL", "noreply@schoolbus.com")
    
    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    
    # FCM
    FCM_CREDENTIALS_PATH: str = os.getenv("FCM_CREDENTIALS_PATH", "")
    
    # CORS
    BACKEND_CORS_ORIGINS: list = ["http://localhost:3000", "http://localhost:8000", "http://localhost:3001", "http://192.168.100.70:3000"]
    
    # Location Updates Retention & Maintenance
    LOCATION_RETENTION_DAYS: int = int(os.getenv("LOCATION_RETENTION_DAYS", "60"))
    ENABLE_LOCATION_AUTO_CLEANUP: bool = os.getenv("ENABLE_LOCATION_AUTO_CLEANUP", "true").lower() in ("true", "1", "yes")
    LOCATION_CLEANUP_INTERVAL_HOURS: int = int(os.getenv("LOCATION_CLEANUP_INTERVAL_HOURS", "24"))
    LOCATION_CLEANUP_BATCH_SIZE: int = int(os.getenv("LOCATION_CLEANUP_BATCH_SIZE", "5000"))
    
    # Currency & Regional (Nepali Rupee - NPR)
    DEFAULT_CURRENCY: str = os.getenv("DEFAULT_CURRENCY", "NPR")
    DEFAULT_CURRENCY_SYMBOL: str = os.getenv("DEFAULT_CURRENCY_SYMBOL", "Rs.")
     
    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"   # <-- Add this line

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
