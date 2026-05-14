from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/crypto_bot")
    
    coinbase_api_key: str
    coinbase_api_secret: str
    coinbase_passphrase: str
    
    trading_pairs: List[str] = ["BTC-USD", "ETH-USD", "XRP-USD"]
    initial_capital_usd: float = 10000.0
    
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    sentiment_threshold: float = 0.5
    
    redis_url: str = "redis://localhost:6379/0"
    
    class Config:
        env_file = ".env"

settings = Settings()
