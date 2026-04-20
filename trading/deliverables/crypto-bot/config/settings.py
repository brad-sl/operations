"""
Configuration loader for Crypto Trading Bot
Reads from .env and validates all required settings
"""

import os
from typing import Optional
from pydantic import BaseSettings, validator


class Settings(BaseSettings):
    """All configuration in one place, validated at startup"""

    # ============================================
    # X (Twitter) API
    # ============================================
    x_bearer_token: str

    # ============================================
    # Coinbase Advanced Trade API
    # ============================================
    coinbase_api_key_id: str
    coinbase_private_key: str
    coinbase_organization_id: Optional[str] = None
    coinbase_sandbox: bool = True

    # ============================================
    # Database
    # ============================================
    database_url: str = "sqlite:///./trading.db"
    database_echo: bool = False

    # ============================================
    # Trading Parameters
    # ============================================
    initial_capital: float = 1000.0  # USD
    risk_per_trade: float = 0.02  # 2%
    target_rsi_high: float = 70.0  # Overbought
    target_rsi_low: float = 30.0  # Oversold
    rsi_period: int = 14

    # ============================================
    # Sentiment Thresholds
    # ============================================
    sentiment_buy_threshold: float = 0.5
    sentiment_sell_threshold: float = -0.5
    sentiment_weight: float = 0.3  # 30% sentiment, 70% RSI

    # ============================================
    # Logging
    # ============================================
    log_level: str = "INFO"
    log_file: str = "logs/trading.log"
    log_max_size_mb: int = 50
    log_backup_count: int = 5

    # ============================================
    # Environment
    # ============================================
    environment: str = "development"  # development, production
    debug: bool = False

    @validator("x_bearer_token")
    def validate_x_bearer_token(cls, v):
        """Ensure X Bearer token is provided and looks valid"""
        if not v or len(v) < 10:
            raise ValueError("X_BEARER_TOKEN must be a valid Bearer token")
        return v

    @validator("coinbase_api_key_id")
    def validate_coinbase_key_id(cls, v):
        """Ensure Coinbase Key ID is UUID format"""
        if not v or len(v) < 10:
            raise ValueError("COINBASE_API_KEY_ID must be provided")
        return v

    @validator("coinbase_private_key")
    def validate_coinbase_private_key(cls, v):
        """Ensure private key looks like PEM format"""
        if not v or "PRIVATE KEY" not in v.upper():
            raise ValueError(
                "COINBASE_PRIVATE_KEY must be in PEM format "
                "(contains 'PRIVATE KEY')"
            )
        return v

    @validator("risk_per_trade")
    def validate_risk(cls, v):
        """Risk per trade must be between 0.1% and 10%"""
        if not (0.001 <= v <= 0.10):
            raise ValueError("risk_per_trade must be between 0.1% and 10%")
        return v

    class Config:
        """Pydantic config"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def get_settings() -> Settings:
    """Load and validate settings from .env"""
    try:
        settings = Settings()
        print(f"✅ Configuration loaded successfully")
        print(f"   Environment: {settings.environment}")
        print(f"   Sandbox: {settings.coinbase_sandbox}")
        print(f"   Capital: ${settings.initial_capital}")
        return settings
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        raise


# Global settings instance
settings = get_settings()
