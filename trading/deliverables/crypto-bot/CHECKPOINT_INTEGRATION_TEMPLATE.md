# Checkpoint Integration Template

For Modules 5-8 of Crypto Bot Phase 2: Signal Generator, Order Executor, Portfolio Tracker, Unit Tests

## Quick Start

Every sub-agent module should follow this pattern to integrate checkpointing:

### 1. Import at Top

```python
import sys
sys.path.insert(0, '/home/brad/.openclaw/workspace/operations/crypto-bot')
from checkpoint_manager import CheckpointManager
```

### 2. Initialize in Main()

```python
def main():
    SESSION_ID = os.getenv("SESSION_ID", "module-5-signal-gen-2026-03-23-default")
    
    checkpointer = CheckpointManager(
        session_id=SESSION_ID,
        agent_name="signal_generator",  # or your module name
        output_dir=f"/home/brad/.openclaw/workspace/projects/orchestrator/agents/{SESSION_ID}",
        total_tasks=TOTAL_TASKS,  # e.g., 100 for signals to generate
        checkpoint_interval=10  # Write checkpoint every 10 tasks
    )
    
    try:
        # Your main loop
        for i in range(TOTAL_TASKS):
            result = generate_signal(i)
            checkpointer.mark_complete(
                task_index=i,
                output=result,
                cost=0.0,  # Add if applicable
                metadata={"theme": result.get("theme")}
            )
        
        # Finalize when complete
        final_state = checkpointer.finalize()
        print(f"✅ Complete! State: {json.dumps(final_state, indent=2)}")
        
    except Exception as e:
        # On error: save state and report recovery point
        print(f"❌ Error: {e}")
        recovery = checkpointer.get_recovery_point()
        print(f"Recovery: {json.dumps(recovery, indent=2)}")
        raise
```

### 3. Read Checkpoint on Resume (Optional)

If resuming from a prior interrupted run:

```python
def load_checkpoint_if_exists(session_id: str, agent_name: str) -> Optional[Dict]:
    """Load existing checkpoint for resumption."""
    checkpoint_file = (
        Path(f"/home/brad/.openclaw/workspace/projects/orchestrator/agents/{session_id}")
        / "STATE.json"
    )
    if checkpoint_file.exists():
        with open(checkpoint_file, "r") as f:
            return json.load(f)
    return None

def main():
    SESSION_ID = os.getenv("SESSION_ID", "...")
    existing_checkpoint = load_checkpoint_if_exists(SESSION_ID, "signal_generator")
    
    if existing_checkpoint:
        print(f"📋 Resuming from checkpoint: {existing_checkpoint['progress']}")
        start_index = existing_checkpoint["progress"]["completed"]
    else:
        print(f"🆕 Starting fresh")
        start_index = 0
    
    checkpointer = CheckpointManager(...)
    
    for i in range(start_index, TOTAL_TASKS):  # Skip completed tasks
        result = generate_signal(i)
        checkpointer.mark_complete(i, result)
```

---

## For Each Module (5-8)

### Module 5: Signal Generator

```python
class SignalGenerator:
    def __init__(self, rsi_data, sentiment_data):
        self.checkpointer = CheckpointManager(
            session_id=os.getenv("SESSION_ID", "signal-gen-default"),
            agent_name="signal_generator",
            output_dir="/workspace/projects/orchestrator/agents/signal-gen",
            total_tasks=len(rsi_data),
            checkpoint_interval=50
        )
    
    def generate_signals(self):
        """Generate trading signals from RSI + sentiment data."""
        for i, (rsi, sentiment) in enumerate(zip(self.rsi_data, self.sentiment_data)):
            signal = {
                "index": i,
                "rsi": rsi,
                "sentiment": sentiment,
                "combined_score": (rsi * 0.7) + (sentiment * 0.3),
                "signal": "BUY" if combined_score > 0.6 else "SELL" if combined_score < -0.6 else "HOLD"
            }
            
            self.checkpointer.mark_complete(
                task_index=i,
                output=signal,
                metadata={"signal_type": signal["signal"]}
            )
        
        return self.checkpointer.finalize()
```

### Module 6: Order Executor

```python
class OrderExecutor:
    def __init__(self, signals, coinbase_client):
        self.checkpointer = CheckpointManager(
            session_id=os.getenv("SESSION_ID", "order-exec-default"),
            agent_name="order_executor",
            output_dir="/workspace/projects/orchestrator/agents/order-exec",
            total_tasks=len(signals),
            checkpoint_interval=5
        )
    
    def execute_orders(self):
        """Execute orders based on signals (paper trading first)."""
        for i, signal in enumerate(self.signals):
            if signal["signal"] in ["BUY", "SELL"]:
                order = self.coinbase_client.create_order(
                    product_id="BTC-USD",
                    side=signal["signal"].lower(),
                    order_type="limit",
                    price=signal.get("price"),
                    size=signal.get("size", 0.01)
                )
                
                self.checkpointer.mark_complete(
                    task_index=i,
                    output=order,
                    cost=order.get("fee", 0),
                    metadata={"order_id": order.get("order_id")}
                )
        
        return self.checkpointer.finalize()
```

### Module 7: Portfolio Tracker

```python
class PortfolioTracker:
    def __init__(self, orders):
        self.checkpointer = CheckpointManager(
            session_id=os.getenv("SESSION_ID", "portfolio-default"),
            agent_name="portfolio_tracker",
            output_dir="/workspace/projects/orchestrator/agents/portfolio",
            total_tasks=len(orders),
            checkpoint_interval=20
        )
    
    def track_portfolio(self):
        """Track portfolio P&L and positions."""
        portfolio = {}
        
        for i, order in enumerate(self.orders):
            # Update portfolio state
            currency = order.get("product_id", "").split("-")[0]
            portfolio[currency] = portfolio.get(currency, 0) + order.get("size", 0)
            
            self.checkpointer.mark_complete(
                task_index=i,
                output={"portfolio_state": portfolio.copy()},
                metadata={"total_btc": portfolio.get("BTC", 0)}
            )
        
        return self.checkpointer.finalize()
```

### Module 8: Unit Tests

```python
import pytest

class TestSignalGenerator:
    def setup_method(self):
        self.checkpointer = CheckpointManager(
            session_id="test-signal-gen",
            agent_name="test_signal_generator",
            output_dir="/workspace/projects/orchestrator/agents/test-signal",
            total_tasks=10
        )
    
    def test_signal_generation(self):
        """Test signal generation with checkpoint tracking."""
        test_cases = [
            {"rsi": 75, "sentiment": 0.8, "expected": "BUY"},
            {"rsi": 25, "sentiment": -0.8, "expected": "SELL"},
        ]
        
        for i, test in enumerate(test_cases):
            signal = generate_signal(test["rsi"], test["sentiment"])
            assert signal == test["expected"]
            
            self.checkpointer.mark_complete(
                task_index=i,
                output={"passed": True},
                metadata={"test_name": f"test_{i}"}
            )
        
        final = self.checkpointer.finalize()
        assert final["progress"]["completed"] == len(test_cases)
```

---

## Checkpoint File Structure

After running with checkpointing enabled, you'll see:

```
/workspace/projects/orchestrator/agents/
├── signal-gen-2026-03-23-abc123/
│   ├── STATE.json           ← Current execution state
│   ├── MANIFEST.json        ← All outputs generated so far
│   ├── RECOVERY.md          ← Human-readable recovery instructions
│   └── [your module outputs]
└── shared/
    └── SESSION_REGISTRY.json ← Central tracking of all sessions
```

---

## Recovery Flow

**If Module 5 crashes after generating 75/100 signals:**

1. Orchestrator reads `SESSION_REGISTRY.json` → Finds session "in_progress"
2. Reads `RECOVERY.md` → "Resume from signal #76"
3. Spawns Module 5 again with checkpoint files attached
4. Module 5 reads checkpoint → "Oh, I've done 0-74. Start with 75."
5. Generates signals 75-100 (skipping duplicates) ✅

---

## Cost/Benefit

| Scenario | Without Checkpointing | With Checkpointing |
|----------|----------------------|-------------------|
| Crash after 75/100 | Restart from 0 (waste resources) | Resume from 75 (minimal waste) |
| Model swap | Context lost | Checkpoint survives |
| Host migration | File paths break | Checkpoints portable |

---

## Testing Checkpointing Locally

```bash
# Run Module 5 standalone with checkpointing
cd /home/brad/.openclaw/workspace/operations/crypto-bot
python -c "
import signal_generator
gen = signal_generator.SignalGenerator(rsi_data=[...], sentiment_data=[...])
gen.generate_signals()
"

# Verify checkpoint files created
ls -la /workspace/projects/orchestrator/agents/signal-gen-*/*.json

# Inspect checkpoint
cat /workspace/projects/orchestrator/agents/signal-gen-*/STATE.json | jq .
```

---

## Summary

✅ **Integrated:** Add 3-5 lines to your module (import, init, mark_complete, finalize)  
✅ **Automatic:** Checkpoints write every N tasks  
✅ **Resumable:** On crash, next spawn detects and resumes  
✅ **Auditable:** SESSION_REGISTRY tracks all runs  
✅ **Zero Breaking Changes:** Optional layer—works with or without  

---

_Ready for Modules 5-8 integration. Begin Phase 2 continuation with confidence._
