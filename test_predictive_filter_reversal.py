from dataclasses import dataclass
from typing import List, Optional

@dataclass
class SentimentRecord:
    timestamp: str
    sentiment: float
    rsi: float

def calculate_velocity(data: List[SentimentRecord], window: int = 3) -> float:
    if len(data) < 2:
        return 0.0
    
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
        # If signal is BUY but velocity is strongly negative (exhaustion), downgrade
        if current_signal == "BUY" and velocity < -0.1 * self.sensitivity:
            return "HOLD"
        # If signal is SELL but velocity is strongly positive (recovery), downgrade
        if current_signal == "SELL" and velocity > 0.1 * self.sensitivity:
            return "HOLD"
        
        return current_signal

# --- Backtest simulating a reversal ---

def run_backtest():
    # Simulated data: Sentiment starting strong but starting to drop (reversal)
    history = [
        SentimentRecord("2026-06-16T04:00:00Z", 0.6, 55.6),
        SentimentRecord("2026-06-16T16:00:00Z", 0.4, 55.3),
        SentimentRecord("2026-06-17T04:00:00Z", 0.1, 55.0),
    ]
    
    filter = PredictiveSignalFilter()
    
    current_signal = "BUY" 
    velocity = calculate_velocity(history)
    
    new_signal = filter.apply_filter(current_signal, velocity)
    
    print(f"Historical Sentiment: {[r.sentiment for r in history]}")
    print(f"Calculated Sentiment Velocity: {velocity:.4f}")
    print(f"Base Signal (Based on high history): {current_signal}")
    print(f"Filtered Signal (Predicting reversal): {new_signal}")

if __name__ == "__main__":
    run_backtest()
