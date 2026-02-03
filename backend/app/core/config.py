"""
Core Configuration Management
KeepGaining Trading Platform

Comprehensive settings management with environment-based configuration,
validation, and runtime updates support.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional, List, Literal
from functools import lru_cache
from pathlib import Path


class DatabaseSettings(BaseSettings):
    """Database connection settings."""
    
    model_config = SettingsConfigDict(env_prefix="DB_")
    
    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, description="Database port")
    user: str = Field(default="user", description="Database user")
    password: str = Field(default="password", description="Database password")
    name: str = Field(default="keepgaining", description="Database name")
    
    # Connection pool settings
    pool_size: int = Field(default=10, description="Connection pool size")
    max_overflow: int = Field(default=20, description="Max overflow connections")
    pool_timeout: int = Field(default=30, description="Pool timeout in seconds")
    pool_recycle: int = Field(default=1800, description="Recycle connections after seconds")
    
    @property
    def async_url(self) -> str:
        """Async database URL for SQLAlchemy."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
    
    @property
    def sync_url(self) -> str:
        """Sync database URL for Alembic migrations."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class RedisSettings(BaseSettings):
    """Redis connection settings."""
    
    model_config = SettingsConfigDict(env_prefix="REDIS_")
    
    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    password: Optional[str] = Field(default=None, description="Redis password")
    db: int = Field(default=0, description="Redis database number")
    
    # Connection pool
    max_connections: int = Field(default=50, description="Max connections")
    socket_timeout: float = Field(default=5.0, description="Socket timeout")
    
    # Streams settings
    stream_max_len: int = Field(default=10000, description="Max stream length")
    consumer_group_prefix: str = Field(default="kg", description="Consumer group prefix")
    
    @property
    def url(self) -> str:
        """Redis URL."""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class FyersSettings(BaseSettings):
    """Fyers broker settings."""
    
    model_config = SettingsConfigDict(env_prefix="FYERS_")
    
    client_id: str = Field(default="", description="Fyers client ID (App ID)")
    secret_key: str = Field(default="", description="Fyers secret key")
    redirect_uri: str = Field(default="https://127.0.0.1:5000/", description="OAuth redirect URI")
    user_id: str = Field(default="", description="Fyers user ID")
    pin: str = Field(default="", description="Fyers PIN")
    totp_key: str = Field(default="", description="TOTP secret for auto-login")
    
    # Rate limits (per second)
    rate_limit_historical: int = Field(default=10, description="Historical data rate limit")
    rate_limit_orders: int = Field(default=10, description="Order placement rate limit")
    rate_limit_quotes: int = Field(default=50, description="Quote requests rate limit")
    
    # WebSocket settings
    ws_reconnect_delay: float = Field(default=5.0, description="WebSocket reconnect delay")
    ws_max_symbols: int = Field(default=100, description="Max symbols per WebSocket")
    
    @property
    def is_configured(self) -> bool:
        """Check if Fyers is properly configured."""
        return bool(self.client_id and self.secret_key and self.user_id)


class UpstoxSettings(BaseSettings):
    """Upstox broker settings (for data)."""
    
    model_config = SettingsConfigDict(env_prefix="UPSTOX_")
    
    api_key: str = Field(default="", description="Upstox API key")
    api_secret: str = Field(default="", description="Upstox API secret")
    redirect_uri: str = Field(default="https://127.0.0.1:5000/callback", description="OAuth redirect URI")
    
    # Credentials for automation
    user_id: str = Field(default="", description="Upstox user ID")
    mobile: str = Field(default="", description="Upstox registered mobile number")
    pin: str = Field(default="", description="Upstox 6-digit PIN")
    totp_secret: str = Field(default="", description="Upstox TOTP secret")
    
    # Rate limits
    rate_limit_historical: int = Field(default=10, description="Historical data rate limit")
    rate_limit_quotes: int = Field(default=25, description="Quote batch rate limit")
    batch_quote_size: int = Field(default=500, description="Max symbols per batch quote")
    
    @property
    def is_configured(self) -> bool:
        """Check if Upstox API keys are configured."""
        return bool(self.api_key and self.api_secret)
        
    @property
    def is_auth_configured(self) -> bool:
        """Check if Upstox auth credentials are configured."""
        return bool(self.mobile and self.pin)


class TradingSettings(BaseSettings):
    """Trading engine settings."""
    
    model_config = SettingsConfigDict(env_prefix="TRADING_")
    
    # Mode
    mode: Literal["LIVE", "PAPER", "BACKTEST"] = Field(default="PAPER", description="Trading mode")
    
    # Market hours (IST)
    market_open_time: str = Field(default="09:15", description="Market open time")
    market_close_time: str = Field(default="15:30", description="Market close time")
    pre_market_start: str = Field(default="09:00", description="Pre-market start")
    
    # Risk defaults
    default_max_positions: int = Field(default=5, description="Default max positions")
    default_position_size_pct: float = Field(default=10.0, description="Default position size %")
    default_sl_pct: float = Field(default=2.0, description="Default stop loss %")
    default_target_pct: float = Field(default=4.0, description="Default target %")
    max_daily_loss_pct: float = Field(default=5.0, description="Max daily loss %")
    
    # Execution
    order_timeout_seconds: int = Field(default=30, description="Order timeout")
    retry_failed_orders: bool = Field(default=True, description="Retry failed orders")
    max_order_retries: int = Field(default=3, description="Max order retries")


class LoggingSettings(BaseSettings):
    """Logging configuration."""
    
    model_config = SettingsConfigDict(env_prefix="LOG_")
    
    level: str = Field(default="INFO", description="Log level")
    format: str = Field(
        default="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        description="Log format"
    )
    
    # File logging
    file_enabled: bool = Field(default=True, description="Enable file logging")
    file_path: str = Field(default="logs/keepgaining.log", description="Log file path")
    file_rotation: str = Field(default="10 MB", description="Log rotation size")
    file_retention: str = Field(default="30 days", description="Log retention period")


class APISettings(BaseSettings):
    """API server settings."""
    
    model_config = SettingsConfigDict(env_prefix="API_")
    
    host: str = Field(default="0.0.0.0", description="API host")
    port: int = Field(default=8000, description="API port")
    debug: bool = Field(default=False, description="Debug mode")
    workers: int = Field(default=1, description="Number of workers")
    
    # CORS
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost"],
        description="Allowed CORS origins"
    )


class Settings(BaseSettings):
    """
    Main application settings.
    
    Aggregates all sub-settings and provides environment-based configuration.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Application
    PROJECT_NAME: str = Field(default="KeepGaining", description="Application name")
    APP_VERSION: str = Field(default="2.0.0", description="Application version")
    ENVIRONMENT: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Environment"
    )
    DEBUG: bool = Field(default=True, description="Debug mode")
    API_V1_STR: str = "/api/v1"
    
    # Allowed origins for CORS (comma-separated in env)
    ALLOWED_ORIGINS: List[str] = Field(
        default=[],
        description="Additional allowed CORS origins"
    )
    
    # Legacy DATABASE_URL support (for backward compatibility)
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://user:password@localhost:5432/keepgaining",
        description="Database URL"
    )
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis URL")
    
    # Fyers credentials
    FYERS_CLIENT_ID: str = Field(default="", description="Fyers client ID")
    FYERS_SECRET_KEY: str = Field(default="", description="Fyers secret key")
    FYERS_REDIRECT_URI: str = Field(default="https://127.0.0.1:5000/", description="Fyers redirect URI")
    FYERS_USER_ID: str = Field(default="", description="Fyers user ID")
    FYERS_PIN: str = Field(default="", description="Fyers PIN")
    FYERS_TOTP_KEY: str = Field(default="", description="Fyers TOTP key")
    
    # Upstox credentials
    UPSTOX_API_KEY: str = Field(default="", description="Upstox API key")
    UPSTOX_API_SECRET: str = Field(default="", description="Upstox API secret")
    UPSTOX_REDIRECT_URI: str = Field(default="https://127.0.0.1:5000/callback", description="Upstox redirect URI")
    
    # AI settings (optional)
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key")
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, description="Anthropic API key")
    COMET_PRO: bool = Field(default=False, description="Enable Comet Pro features")
    
    @property
    def db(self) -> DatabaseSettings:
        """Get database settings."""
        return DatabaseSettings()
    
    @property
    def redis(self) -> RedisSettings:
        """Get Redis settings."""
        return RedisSettings()
    
    @property
    def fyers(self) -> FyersSettings:
        """Get Fyers settings with backward compatibility."""
        return FyersSettings(
            client_id=self.FYERS_CLIENT_ID,
            secret_key=self.FYERS_SECRET_KEY,
            redirect_uri=self.FYERS_REDIRECT_URI,
            user_id=self.FYERS_USER_ID,
            pin=self.FYERS_PIN,
            totp_key=self.FYERS_TOTP_KEY,
        )
    
    @property
    def upstox(self) -> UpstoxSettings:
        """Get Upstox settings."""
        return UpstoxSettings(
            api_key=self.UPSTOX_API_KEY,
            api_secret=self.UPSTOX_API_SECRET,
            redirect_uri=self.UPSTOX_REDIRECT_URI,
        )
    
    @property
    def trading(self) -> TradingSettings:
        """Get trading settings."""
        return TradingSettings()
    
    @property
    def logging(self) -> LoggingSettings:
        """Get logging settings."""
        return LoggingSettings()
    
    @property
    def api(self) -> APISettings:
        """Get API settings."""
        return APISettings()
    
    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.ENVIRONMENT == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.ENVIRONMENT == "development"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Uses lru_cache to ensure settings are only loaded once.
    Call get_settings.cache_clear() to reload settings.
    """
    return Settings()


# Global settings instance for backward compatibility
settings = get_settings()


# Utility functions
def reload_settings() -> Settings:
    """Reload settings from environment."""
    get_settings.cache_clear()
    return get_settings()


def get_base_path() -> Path:
    """Get the base path of the application."""
    return Path(__file__).parent.parent.parent


def get_data_path() -> Path:
    """Get the data directory path."""
    path = get_base_path() / "data"
    path.mkdir(exist_ok=True)
    return path


def get_logs_path() -> Path:
    """Get the logs directory path."""
    path = get_base_path() / "logs"
    path.mkdir(exist_ok=True)
    return path
