import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").lower()
        
        # Database
        self.DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres@127.0.0.1:5432/releaseguard"
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", self.DEFAULT_DATABASE_URL)
        
        # Redis
        self.DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"
        self.REDIS_URL: str = os.getenv("REDIS_URL", self.DEFAULT_REDIS_URL)
        
        # Authentication & JWT
        self.DEFAULT_JWT_SECRET = "releaseguard-super-secret-jwt-key-2026"
        self.JWT_SECRET: str = os.getenv("JWT_SECRET", self.DEFAULT_JWT_SECRET)
        self.JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
        self.JWT_EXPIRATION_MINUTES: int = int(os.getenv("JWT_EXPIRATION_MINUTES", "1440"))
        
        # Security & CORS
        cors_raw = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173")
        self.CORS_ORIGINS: List[str] = [origin.strip() for origin in cors_raw.split(",") if origin.strip()]
        
        # Payload size limits (bytes)
        self.MAX_PAYLOAD_SIZE: int = int(os.getenv("MAX_PAYLOAD_SIZE", str(1 * 1024 * 1024)))  # 1MB
        self.MAX_BULK_PAYLOAD_SIZE: int = int(os.getenv("MAX_BULK_PAYLOAD_SIZE", str(5 * 1024 * 1024)))  # 5MB
        
        # Ingestion limits
        self.MAX_BULK_EVENTS: int = int(os.getenv("MAX_BULK_EVENTS", "100"))
        
        # Pagination
        self.DEFAULT_PAGE_LIMIT: int = 20
        self.MAX_PAGE_LIMIT: int = 100
        
        # Rate Limiting
        self.AUTH_MAX_ATTEMPTS: int = int(os.getenv("AUTH_MAX_ATTEMPTS", "5"))
        self.AUTH_LOCKOUT_SECONDS: int = int(os.getenv("AUTH_LOCKOUT_SECONDS", "900"))  # 15 minutes

    def validate_production(self) -> None:
        """Validates critical security configuration for production deployments."""
        if self.ENVIRONMENT == "production":
            errors = []
            if self.JWT_SECRET == self.DEFAULT_JWT_SECRET or len(self.JWT_SECRET) < 32:
                errors.append("JWT_SECRET must be configured with a strong secret (at least 32 characters) in production")
            if self.DATABASE_URL.startswith("sqlite"):
                errors.append("SQLite is not supported in production. Configure a production PostgreSQL DATABASE_URL")
            if not self.REDIS_URL:
                errors.append("REDIS_URL must be configured in production")
            if "*" in self.CORS_ORIGINS:
                errors.append("Wildcard CORS origins are forbidden in production")
            if errors:
                raise ValueError("Production configuration validation failed:\n - " + "\n - ".join(errors))


settings = Settings()
