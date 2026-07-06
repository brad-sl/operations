"""
trading/types.py - shared types for platform executor layer.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class TradeResult:
    """Result of a trade execution (buy/sell or plan action)."""
    success: bool = False
    order_id: Optional[str] = None
    pair: Optional[str] = None
    action: Optional[str] = None
    usd_amount: Optional[float] = None
    size: Optional[float] = None
    qty: Optional[float] = None  # alias
    entry_price: Optional[float] = None
    price: Optional[float] = None
    sl_attached: bool = False
    tp_attached: bool = False
    error: Optional[str] = None
    classified: Optional[Dict[str, Any]] = None
    recovery_suggestion: Optional[Dict[str, Any]] = None
    actual_fill_used: bool = False

    def __post_init__(self):
        if self.size is None and self.qty is not None:
            self.size = self.qty
        if self.qty is None and self.size is not None:
            self.qty = self.size

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "order_id": self.order_id,
            "pair": self.pair,
            "action": self.action,
            "usd_amount": self.usd_amount,
            "size": self.size,
            "qty": self.qty,
            "entry_price": self.entry_price,
            "price": self.price,
            "sl_attached": self.sl_attached,
            "tp_attached": self.tp_attached,
            "error": self.error,
            "classified": self.classified,
            "recovery_suggestion": self.recovery_suggestion,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TradeResult":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

# For compatibility with attribute and .get access in executor paths
class AttrDict(dict):
    """Dict that supports attribute access too."""
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)
    def __setattr__(self, key, value):
        self[key] = value

# Re-export common
__all__ = ["TradeResult", "AttrDict"]
