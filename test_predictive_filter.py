
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class SentimentRecord:
    timestamp: str
    sentiment: float
    rsi: float

def calculate_velocity(data: List[SentimentRecord], window: int = 3) -> float:
    """Calculate the simple velocity (average period-over-period change) over a window."""
    if len(data) < 2:
        return 0.0
    
    # Analyze the last 'window' records
    relevant_data = data[-window:]
    changes = []
    
    for i in range(1, len(relevant_data)):
        change = relevant_data[i].sentiment - relevant_data[i-1].sentiment
        changes.append(change)
        
    return sum(changes) / len(changes)

class PredictiveSignalFilter:
    def __init__(self, sensitivity: float = 0.5):
        self.sensitivity = sensitivity

    def apply_filter(self, current_signal: str, velocity: float) -> str:
        """Modifies signal based on velocity."""
        # If signal is BUY but velocity is strongly negative, downgrade to HOLD
        if current_signal == "BUY" and velocity < -0.1 * self.sensitivity:
            return "HOLD"
        # If signal is SELL but velocity is strongly positive, downgrade to HOLD
        if current_signal == "SELL" and velocity > 0.1 * self.sensitivity:
            return "HOLD"
        
        return current_signal

# --- Mock Backtest ---

def run_backtest():
    # Simulated data: Sentiment starting at 0.1 and increasing
    history = [
        SentimentRecord("2026-06-16T04:00:00Z", 0.1, 55.0),
        SentimentRecord("2026-06-16T16:00:00Z", 0.3, 55.3),
        SentimentRecord("2026-06-17T04:00:00Z", 0.6, 55.6),
    ]
    
    filter = PredictiveSignalFilter()
    
    # Mocking signal generation for the latest point
    # RSI 55.6, Sentiment 0.6 -> Weighted score ~0.3 -> BUY
    current_signal = "BUY" 
    velocity = calculate_velocity(history)
    
    new_signal = filter.apply_filter(current_signal, velocity)
    
    print(f"Historical Sentiment: {[r.sentiment for r in history]}")
    print(f"Calculated Sentiment Velocity: {velocity:.4f}")
    print(f"Base Signal: {current_signal}")
    print(f"Filtered Signal: {new_signal}")

if __name__ == "__main__":
    run_backtest()
