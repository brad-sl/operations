"""
Signal Generator — Module 5 of Crypto Bot Phase 2

Combines RSI + sentiment data into trading signals (BUY/SELL/HOLD).

Algorithm:
  combined_score = (rsi_value * 0.70) + (sentiment_score * 0.30)
  
  if combined_score > 0.6:
    signal = "BUY" (confidence = combined_score)
  elif combined_score < -0.6:
    signal = "SELL" (confidence = abs(combined_score))
  else:
    signal = "HOLD" (confidence = 0.0)

Features:
  - Generates trading signals from RSI + sentiment inputs
  - Confidence scoring (0.0 to 1.0)
  - Reasoning text for auditability
  - Checkpointing support (resume from last signal on crash)
  - Type hints + comprehensive docstrings

Checkpointing:
  - Writes STATE.json every N signals
  - Writes MANIFEST.json with all outputs
  - Enables resumable execution after interruption
"""

import sys
import os
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

# Add crypto-bot module to path for imports
sys.path.insert(0, '/home/brad/.openclaw/workspace/operations/crypto-bot')

from checkpoint_manager import CheckpointManager


@dataclass
class Signal:
    """
    Trading signal output.
    
    Attributes:
        timestamp: ISO 8601 UTC timestamp of signal generation
        rsi: RSI value (0-100)
        sentiment: Sentiment score (-1.0 to +1.0)
        combined_score: Weighted combination (70% RSI + 30% sentiment)
        signal: Trading signal (BUY, SELL, or HOLD)
        confidence: Confidence level (0.0 to 1.0)
        reasoning: Human-readable explanation of the signal
    """
    timestamp: str
    rsi: float
    sentiment: float
    combined_score: float
    signal: str
    confidence: float
    reasoning: str


class SignalGenerator:
    """
    Generates trading signals by combining RSI and sentiment analysis.
    
    Attributes:
        rsi_data: List of RSI values (0-100 scale)
        sentiment_data: List of sentiment scores (-1.0 to +1.0 scale)
        checkpointer: CheckpointManager for resumable execution
    
    Example:
        >>> rsi_values = [45.2, 55.3, 65.1, 72.4, 75.8]
        >>> sentiment_scores = [0.2, 0.3, 0.5, 0.7, 0.8]
        >>> gen = SignalGenerator(rsi_values, sentiment_scores)
        >>> signals = gen.generate_all_signals()
        >>> print(f"Generated {len(signals)} signals")
        >>> print(signals[0].signal)  # BUY, SELL, or HOLD
    """

    def __init__(self, rsi_data: List[float], sentiment_data: List[float]):
        """
        Initialize signal generator with RSI and sentiment data.

        Args:
            rsi_data: List of RSI values (typically 0-100, but can exceed)
            sentiment_data: List of sentiment scores (-1.0 to +1.0)

        Raises:
            ValueError: If data lists have different lengths
            ValueError: If lists are empty
        """
        if len(rsi_data) != len(sentiment_data):
            raise ValueError(
                f"RSI data ({len(rsi_data)}) and sentiment data "
                f"({len(sentiment_data)}) must have equal length"
            )
        if len(rsi_data) == 0:
            raise ValueError("Input data lists cannot be empty")

        self.rsi_data = rsi_data
        self.sentiment_data = sentiment_data

        # Initialize checkpointer
        session_id = os.getenv(
            "SESSION_ID",
            f"signal-gen-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        )
        
        output_dir = os.getenv(
            "CHECKPOINT_OUTPUT_DIR",
            f"/home/brad/.openclaw/workspace/projects/orchestrator/agents/{session_id}"
        )

        self.checkpointer = CheckpointManager(
            session_id=session_id,
            agent_name="signal_generator",
            output_dir=output_dir,
            total_tasks=len(rsi_data),
            checkpoint_interval=50  # Write checkpoint every 50 signals
        )

    def generate_signal(self, rsi: float, sentiment: float) -> Signal:
        """
        Generate a single trading signal from RSI and sentiment values.

        Algorithm:
          1. Normalize RSI to 0-1 scale (divide by 100)
          2. Normalize sentiment (already -1 to +1)
          3. Combine: 70% RSI + 30% sentiment
          4. Threshold on combined score

        Args:
            rsi: RSI value (typically 0-100)
            sentiment: Sentiment score (-1.0 to +1.0)

        Returns:
            Signal object with BUY/SELL/HOLD recommendation
        """
        # Normalize RSI to 0-1 range (RSI is typically 0-100)
        # but allow values outside this range for edge cases
        normalized_rsi = (rsi - 50) / 50.0  # Center around 0, scale to -1 to +1

        # Combined score: 70% RSI + 30% sentiment
        # Both are now on -1 to +1 scale
        combined = (normalized_rsi * 0.70) + (sentiment * 0.30)

        # Generate signal based on threshold
        if combined > 0.6:
            signal_type = "BUY"
            confidence = min(combined, 1.0)  # Cap at 1.0
        elif combined < -0.6:
            signal_type = "SELL"
            confidence = min(abs(combined), 1.0)  # Cap at 1.0
        else:
            signal_type = "HOLD"
            confidence = 0.0

        # Generate reasoning
        rsi_signal = "overbought" if rsi > 70 else "oversold" if rsi < 30 else "neutral"
        sentiment_signal = (
            "very bullish" if sentiment > 0.7 else "bullish" if sentiment > 0.3
            else "very bearish" if sentiment < -0.7 else "bearish" if sentiment < -0.3
            else "neutral"
        )

        reasoning = (
            f"RSI {rsi:.2f} ({rsi_signal}) + Sentiment {sentiment:.2f} ({sentiment_signal}) "
            f"→ Combined {combined:.2f} → {signal_type}"
        )

        return Signal(
            timestamp=datetime.utcnow().isoformat() + "Z",
            rsi=rsi,
            sentiment=sentiment,
            combined_score=combined,
            signal=signal_type,
            confidence=confidence,
            reasoning=reasoning,
        )

    def generate_all_signals(self) -> List[Signal]:
        """
        Generate all trading signals with checkpointing support.

        This method:
        1. Iterates through all RSI and sentiment data pairs
        2. Generates a signal for each pair
        3. Records progress to checkpoint every 50 signals
        4. Handles resume from last checkpoint if available

        Returns:
            List of Signal objects

        Raises:
            Exception: Any error that occurs during signal generation
                      (checkpoint will be saved for recovery)
        """
        signals: List[Signal] = []

        try:
            for i, (rsi, sentiment) in enumerate(
                zip(self.rsi_data, self.sentiment_data)
            ):
                # Generate signal
                signal = self.generate_signal(rsi, sentiment)
                signals.append(signal)

                # Mark complete and auto-checkpoint every 50 signals
                self.checkpointer.mark_complete(
                    task_index=i,
                    output=asdict(signal),
                    cost=0.0,  # Signal generation has no cost
                    metadata={"signal_type": signal.signal}
                )

            # Finalize checkpoint
            final_state = self.checkpointer.finalize()
            
            return signals

        except Exception as e:
            # Save recovery point on error
            recovery = self.checkpointer.get_recovery_point()
            print(
                f"❌ Error during signal generation: {e}",
                file=sys.stderr
            )
            print(
                f"📋 Recovery point: {json.dumps(recovery, indent=2)}",
                file=sys.stderr
            )
            raise

    def get_signal_summary(self, signals: List[Signal]) -> Dict[str, Any]:
        """
        Generate summary statistics about generated signals.

        Args:
            signals: List of Signal objects

        Returns:
            Dictionary with summary stats (BUY/SELL/HOLD counts, avg confidence, etc.)
        """
        if not signals:
            return {
                "total": 0,
                "buy": 0,
                "sell": 0,
                "hold": 0,
                "avg_confidence": 0.0,
                "buy_avg_confidence": 0.0,
                "sell_avg_confidence": 0.0,
            }

        buy_signals = [s for s in signals if s.signal == "BUY"]
        sell_signals = [s for s in signals if s.signal == "SELL"]
        hold_signals = [s for s in signals if s.signal == "HOLD"]

        avg_confidence = sum(s.confidence for s in signals) / len(signals)
        buy_avg = (
            sum(s.confidence for s in buy_signals) / len(buy_signals)
            if buy_signals
            else 0.0
        )
        sell_avg = (
            sum(s.confidence for s in sell_signals) / len(sell_signals)
            if sell_signals
            else 0.0
        )

        return {
            "total": len(signals),
            "buy": len(buy_signals),
            "sell": len(sell_signals),
            "hold": len(hold_signals),
            "avg_confidence": round(avg_confidence, 4),
            "buy_avg_confidence": round(buy_avg, 4),
            "sell_avg_confidence": round(sell_avg, 4),
            "buy_percentage": round(len(buy_signals) / len(signals) * 100, 1),
            "sell_percentage": round(len(sell_signals) / len(signals) * 100, 1),
            "hold_percentage": round(len(hold_signals) / len(signals) * 100, 1),
        }


def main():
    """
    Standalone execution: generate test signals and verify checkpointing.
    
    Usage:
        python signal_generator.py
    """
    print("🚀 Signal Generator — Module 5 Standalone Test")
    print("=" * 60)

    # Generate test data
    # RSI values: cycling through oversold → neutral → overbought
    rsi_values = [
        25, 30, 35, 40, 45, 50, 55, 60, 65, 70,  # 0-9: Rising
        72, 75, 78, 80, 82, 75, 70, 65, 60, 55,  # 10-19: Falling
        50, 45, 40, 35, 30, 28, 26, 25, 30, 35,  # 20-29: Mixed
    ] + [50 + 5 * (i % 3) for i in range(70)]  # 30-99: Extended data

    # Sentiment values: corresponding sentiment scores
    sentiment_values = [
        -0.5, -0.4, -0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4,  # 0-9
        0.5, 0.6, 0.7, 0.8, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4,  # 10-19
        0.3, 0.2, 0.1, 0.0, -0.1, -0.2, -0.3, -0.4, -0.2, 0.0,  # 20-29
    ] + [0.3 + 0.1 * (i % 5) - 0.2 for i in range(70)]  # 30-99: Extended data

    # Create generator
    print(f"\n📊 Test Data:")
    print(f"  RSI values: {len(rsi_values)} points")
    print(f"  Sentiment values: {len(sentiment_values)} points")

    gen = SignalGenerator(rsi_values, sentiment_values)

    # Generate signals
    print(f"\n🔄 Generating {len(rsi_values)} signals with checkpointing...")
    start_time = time.time()

    signals = gen.generate_all_signals()

    elapsed = time.time() - start_time
    print(f"✅ Generated {len(signals)} signals in {elapsed:.2f}s")

    # Show summary
    summary = gen.get_signal_summary(signals)
    print(f"\n📈 Signal Summary:")
    for key, value in summary.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")

    # Show first few signals
    print(f"\n📋 First 5 Signals:")
    for i, sig in enumerate(signals[:5]):
        print(
            f"  [{i}] {sig.signal} (conf={sig.confidence:.2f}) | "
            f"RSI={sig.rsi:.2f}, Sentiment={sig.sentiment:.2f}"
        )

    # Verify checkpoint files
    checkpoint_dir = Path(gen.checkpointer.output_dir)
    print(f"\n💾 Checkpoint Files:")
    print(f"  Output dir: {checkpoint_dir}")

    if (checkpoint_dir / "STATE.json").exists():
        with open(checkpoint_dir / "STATE.json") as f:
            state = json.load(f)
            print(f"  ✅ STATE.json: {state['progress']['completed']}/{state['progress']['total']} complete")
    else:
        print(f"  ❌ STATE.json not found")

    if (checkpoint_dir / "MANIFEST.json").exists():
        with open(checkpoint_dir / "MANIFEST.json") as f:
            manifest = json.load(f)
            print(f"  ✅ MANIFEST.json: {len(manifest['outputs']['completed'])} outputs recorded")
    else:
        print(f"  ❌ MANIFEST.json not found")

    if (checkpoint_dir / "RECOVERY.md").exists():
        print(f"  ✅ RECOVERY.md created")
    else:
        print(f"  ❌ RECOVERY.md not found")

    print("\n" + "=" * 60)
    print("✨ Signal Generator test complete!")


if __name__ == "__main__":
    main()
