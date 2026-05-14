from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()

class TradeStatus(enum.Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"

class SignalAction(enum.Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"

class Trader(Base):
    __tablename__ = "traders"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    trades = relationship("Trade", back_populates="trader")
    signals = relationship("Signal", back_populates="trader")

class Pair(Base):
    __tablename__ = "pairs"
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), unique=True, nullable=False)  # e.g., BTC-USD
    
    prices = relationship("Price", back_populates="pair")
    trades = relationship("Trade", back_populates="pair")
    signals = relationship("Signal", back_populates="pair")

class Price(Base):
    __tablename__ = "prices"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pair_id = Column(Integer, ForeignKey("pairs.id"), nullable=False)
    price = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    pair = relationship("Pair", back_populates="prices")

class Trade(Base):
    __tablename__ = "trades"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trader_id = Column(UUID(as_uuid=True), ForeignKey("traders.id"), nullable=False)
    pair_id = Column(Integer, ForeignKey("pairs.id"), nullable=False)
    side = Column(SQLEnum("buy", "sell", name="side_enum"), nullable=False)
    amount = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    status = Column(SQLEnum(TradeStatus), default=TradeStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    trader = relationship("Trader", back_populates="trades")
    pair = relationship("Pair", back_populates="trades")

class Signal(Base):
    __tablename__ = "signals"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trader_id = Column(UUID(as_uuid=True), ForeignKey("traders.id"), nullable=False)
    pair_id = Column(Integer, ForeignKey("pairs.id"), nullable=False)
    rsi = Column(Float)
    sentiment = Column(Float)
    action = Column(SQLEnum(SignalAction))
    confidence = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    trader = relationship("Trader", back_populates="signals")
    pair = relationship("Pair", back_populates="signals")
