#!/usr/bin/env python3
"""
phase4c_multi_pair.py — Multi-Pair Trading Harness with DynamicRSI

ARCHITECTURE: See docs/CRYPTO_BOT_ARCHITECTURE.md before touching this file.

Wires together:
  - DynamicRSISignalCalculator  (regime-aware BUY/SELL/HOLD signals)
  - XSentimentFetcher           (X API sentiment, 4h cache, failover)
  - CoinbaseWrapper / TestPriceWrapper  (real or snapshot prices)
  - SQLite trade log            (phase4_trades.db)

Usage:
  # Snapshot smoke test (deterministic, no API calls):
  PRICE_SOURCE=snapshot python3 phase4c_multi_pair.py --cycles 20

  # Live paper trade (30-min validation, 6 cycles):
  PRICE_SOURCE=coinbase python3 phase4c_multi_pair.py --cycles 6

  # Full 24h multi-pair paper run:
  PRICE_SOURCE=coinbase python3 phase4c_multi_pair.py

Config: config/trading_config.json  (never hardcode here)
DO NOT MODIFY: indicators/, coinbase_wrapper.py, test_price_wrapper.py
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Path setup ──────────────────────────────────────────────────────────────
BOT_DIR = Path(__file__).parent
sys.path.insert(0, str(BOT_DIR))

from dotenv import load_dotenv
load_dotenv(BOT_DIR / '.env')

# ── Canonical imports (see CRYPTO_BOT_ARCHITECTURE.md) ──────────────────────
from indicators.dynamic_rsi_strategy import DynamicRSISignalCalculator, SignalContext
from x_sentiment_fetcher import XSentimentFetcher
from test_price_wrapper import get_price_wrapper

# ── Logging ─────────────────────────────────────────────────────────────────
LOG_DIR = BOT_DIR / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / 'phase4c_run.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
DB_PATH = BOT_DIR / 'phase4_trades.db'
CONFIG_PATH = BOT_DIR / 'config' / 'trading_config.json'
DEFAULT_CONFIG = {
    "pairs": ["BTC-USD", "XRP-USD", "DOGE-USD", "ETH-USD"],
    "cycle_interval_seconds": 300,
    "rsi_period": 14,
    "price_history_window": 50,
    "min_hold_cycles": 3,
    "stop_loss_pct": -0.02,
    "take_profit_pct": 0.015,
    "daily_loss_cap_usd": 50,
    "paper_capital_usd": 1000,
    "total_cycles": 288
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        logger.info(f"Loaded config from {CONFIG_PATH}")
        return {**DEFAULT_CONFIG, **cfg}
    logger.warning(f"No trading_config.json found, using defaults")
    return DEFAULT_CONFIG


def compute_rsi(prices: List[float], period: int = 14) -> float:
    """Compute RSI from rolling price list. Returns 50.0 if insufficient data."""
    if len(prices) < period + 1:
        return 50.0
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 0.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def init_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL NOT NULL,
            pnl REAL,
            pnl_pct REAL,
            entry_time TEXT,
            exit_time TEXT,
            strategy TEXT,
            sentiment_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    logger.info(f"DB ready: {DB_PATH}")


def log_trade(pair: str, entry_px: float, exit_px: float,
              entry_time: str, sentiment: float, strategy: str = "phase4c"):
    pnl = exit_px - entry_px
    pnl_pct = pnl / entry_px if entry_px > 0 else 0.0
    exit_time = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO trades (pair, entry_price, exit_price, pnl, pnl_pct, "
        "entry_time, exit_time, strategy, sentiment_score) VALUES (?,?,?,?,?,?,?,?,?)",
        (pair, entry_px, exit_px, pnl, pnl_pct, entry_time, exit_time, strategy, sentiment)
    )
    conn.commit()
    conn.close()
    direction = "WIN" if pnl >= 0 else "LOSS"
    logger.info(
        f"TRADE CLOSED [{direction}] {pair} "
        f"entry=${entry_px:.4f} exit=${exit_px:.4f} "
        f"P&L=${pnl:.4f} ({pnl_pct:+.2%}) sentiment={sentiment:+.2f}"
    )
    return pnl, pnl_pct


# ── Main Orchestrator ─────────────────────────────────────────────────────────

class Phase4cOrchestrator:
    def __init__(self, cfg: dict):
        self.early_entry = cfg.get('early_entry', False)
        self.cfg = cfg
        self.pairs = cfg["pairs"]
        self.cycle_interval = cfg["cycle_interval_seconds"]
        self.rsi_period = cfg["rsi_period"]
        self.history_window = cfg["price_history_window"]
        self.min_hold_cycles = cfg["min_hold_cycles"]
        self.stop_loss_pct = cfg["stop_loss_pct"]
        self.take_profit_pct = cfg["take_profit_pct"]
        self.daily_loss_cap = cfg["daily_loss_cap_usd"]
        self.total_cycles = cfg["total_cycles"]

        # State per pair
        self.price_history: Dict[str, List[float]] = defaultdict(list)
        self.price_history_ts: Dict[str, List[Tuple[float, datetime]]] = defaultdict(list)
        self.open_positions: Dict[str, dict] = {}
        self.daily_pnl: Dict[str, float] = defaultdict(float)
        self.trade_count = 0
        self.cycle_count = 0
        self.start_time = datetime.now(timezone.utc)
        self.closed_trades: List[dict] = []

        # Core modules (verified against CRYPTO_BOT_ARCHITECTURE.md)
        self.signal_calc = DynamicRSISignalCalculator()
        self.sentiment_fetcher = XSentimentFetcher(cache_dir=str(LOG_DIR))
        self.price_wrapper = get_price_wrapper()

        logger.info("=" * 60)
        logger.info("Phase 4c Multi-Pair Orchestrator INITIALIZED")
        logger.info(f"  Pairs: {self.pairs}")
        logger.info(f"  Cycles: {self.total_cycles} × {self.cycle_interval}s")
        logger.info(f"  RSI period: {self.rsi_period} | Hold: {self.min_hold_cycles} cycles")
        logger.info(f"  Stop loss: {self.stop_loss_pct:.0%} | TP: {self.take_profit_pct:.0%}")
        logger.info(f"  PRICE_SOURCE: {os.getenv('PRICE_SOURCE','coinbase')}")
        logger.info("=" * 60)

    def run_cycle(self):
        self.cycle_count += 1
        now = datetime.utcnow()  # tz-naive to match DynamicRSI detector internals
        logger.info(f"\n{'─'*60}\nCYCLE {self.cycle_count}/{self.total_cycles} — {now.isoformat()}\n{'─'*60}")

        for pair in self.pairs:
            try:
                self._process_pair(pair, now)
            except Exception as e:
                logger.error(f"[{pair}] Cycle error: {e}", exc_info=True)

    def _process_pair(self, pair: str, now: datetime):
        # 1. Fetch price
        price_result = self.price_wrapper.get_price(pair)
        if not price_result.get("success"):
            logger.warning(f"[{pair}] Price fetch failed, skipping")
            return
        current_price = float(price_result["price"])

        # 2. Update rolling price history
        self.price_history[pair].append(current_price)
        if len(self.price_history[pair]) > self.history_window:
            self.price_history[pair].pop(0)
        self.price_history_ts[pair].append((current_price, now))
        if len(self.price_history_ts[pair]) > self.history_window:
            self.price_history_ts[pair].pop(0)

        # 3. Compute RSI from real price history
        rsi = compute_rsi(self.price_history[pair], self.rsi_period)

        # 4. Fetch sentiment (cached 4h per config)
        try:
            sentiment_score, s_meta = self.sentiment_fetcher.get_sentiment(pair)
        except Exception:
            sentiment_score, s_meta = 0.0, {"source": "error"}

        # 5. Generate signal via DynamicRSISignalCalculator
        ctx: SignalContext = self.signal_calc.calculate_signal(
            pair=pair,
            current_price=current_price,
            rsi=rsi,
            sentiment_score=sentiment_score,
            price_history=self.price_history_ts[pair],
            candles=[],
        )

        logger.info(
            f"[{pair}] ${current_price:.4f} | RSI={rsi:.1f} | "
            f"Regime={ctx.regime} | Thresh={ctx.thresholds} | "
            f"Sig={ctx.signal} (conf={ctx.confidence:.2f}) | "
            f"Weighted={ctx.weighted_signal:.1f} | Sent={sentiment_score:+.2f} "
            f"[{s_meta.get('source','?')}]"
        )

        # 6. Check exit on open position first
        if pair in self.open_positions:
            pos = self.open_positions[pair]
            hold = self.cycle_count - pos["entry_cycle"]
            pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"]

            if hold < self.min_hold_cycles:
                logger.info(f"[{pair}] Hold {hold}/{self.min_hold_cycles} cycles (too young)")
                return

            hit_tp = pnl_pct >= self.take_profit_pct
            hit_sl = pnl_pct <= self.stop_loss_pct
            signal_exit = ctx.signal == "SELL"

            if hit_tp or hit_sl or signal_exit:
                reason = "TP" if hit_tp else ("SL" if hit_sl else "SIGNAL")
                pnl, pnl_pct_real = log_trade(
                    pair=pair,
                    entry_px=pos["entry_price"],
                    exit_px=current_price,
                    entry_time=pos["entry_time"],  # already isoformat string
                    sentiment=sentiment_score
                )
                self.daily_pnl[pair] += pnl
                self.trade_count += 1
                self.closed_trades.append({
                    "pair": pair, "pnl": pnl, "pnl_pct": pnl_pct_real,
                    "reason": reason, "hold_cycles": hold
                })
                del self.open_positions[pair]
                logger.info(f"[{pair}] EXIT [{reason}] hold={hold} P&L={pnl_pct:+.2%}")
            else:
                logger.info(f"[{pair}] Hold {hold}/{self.min_hold_cycles} P&L={pnl_pct:+.2%}")
            return

        # 7. Daily loss cap check
        if self.daily_pnl[pair] <= -self.daily_loss_cap:
            logger.warning(f"[{pair}] Daily loss cap hit (${self.daily_pnl[pair]:.2f}), skipping entry")
            return

        # Early entry override
        if self.early_entry and rsi < 40 and ctx.confidence > 0.3 and ctx.signal != "SELL":
            logger.info(f"[{pair}] 🔥 EARLY ENTRY BUY OVERRIDE: RSI={rsi:.1f}<40 conf={ctx.confidence:.2f}>0.3")
            ctx.signal = "BUY"
            ctx.position_size_multiplier = min(2.33, ctx.position_size_multiplier * 2.33)  # Pyramid $150->~$350 equiv
            ctx.weighted_signal = 1.0

        # 8. Entry
        if ctx.signal == "BUY":
            self.open_positions[pair] = {
                "entry_price": current_price,
                "entry_cycle": self.cycle_count,
                "entry_time": datetime.utcnow().isoformat(),
                "sentiment": sentiment_score,
                "regime": str(ctx.regime),
                "size_mult": ctx.position_size_multiplier,
            }
            logger.info(
                f"[{pair}] ENTRY BUY @ ${current_price:.4f} | "
                f"regime={ctx.regime} | size_mult={ctx.position_size_multiplier}x"
            )

    def print_summary(self):
        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds() / 3600
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 4C RUN COMPLETE")
        logger.info(f"  Cycles: {self.cycle_count} | Elapsed: {elapsed:.2f}h")
        logger.info(f"  Closed trades: {self.trade_count}")
        logger.info(f"  Open positions: {list(self.open_positions.keys())}")

        if self.closed_trades:
            wins = [t for t in self.closed_trades if t["pnl"] > 0]
            losses = [t for t in self.closed_trades if t["pnl"] <= 0]
            total_pnl = sum(t["pnl"] for t in self.closed_trades)
            win_rate = len(wins) / len(self.closed_trades) * 100
            logger.info(f"\n  Win rate: {win_rate:.1f}% ({len(wins)}W / {len(losses)}L)")
            logger.info(f"  Total P&L: ${total_pnl:.4f}")
            for pair in self.pairs:
                pair_trades = [t for t in self.closed_trades if t["pair"] == pair]
                if pair_trades:
                    pair_pnl = sum(t["pnl"] for t in pair_trades)
                    logger.info(f"  {pair}: {len(pair_trades)} trades | P&L ${pair_pnl:.4f}")
        else:
            logger.info("  ⚠️  ZERO closed trades — check signal thresholds and hold logic")

        logger.info("=" * 60)


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Phase 4c Multi-Pair Trading Harness")
    parser.add_argument("--cycles", type=int, default=None, help="Override total cycles (default from config)")
    parser.add_argument("--paper-early", action="store_true", help="Enable early entry paper test: BUY if RSI<40 & conf>0.3, pyramid sizing")
    parser.add_argument("--seed-entries", action="store_true", help="Seed one open position per pair at start (smoke test only)")
    args = parser.parse_args()

    init_db()
    cfg = load_config()

    cfg['early_entry'] = args.paper_early
    if args.paper_early:
        LOG_FILE = LOG_DIR / 'early_entry_paper.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(LOG_FILE),
                logging.StreamHandler(sys.stdout),
            ]
        )
        logger = logging.getLogger(__name__)
        logger.info("EARLY ENTRY PAPER TEST MODE ACTIVATED")

    if args.cycles:
        cfg["total_cycles"] = args.cycles
        logger.info(f"Cycles overridden to {args.cycles} (interval={cfg['cycle_interval_seconds']}s)")

    orchestrator = Phase4cOrchestrator(cfg)

    # Smoke test: seed one open position per pair so exit logic is exercised
    if args.seed_entries:
        logger.info("[SMOKE TEST] Seeding open positions for all pairs")
        for pair in cfg["pairs"]:
            seed_price = {"BTC-USD": 65000.0, "XRP-USD": 2.40, "DOGE-USD": 0.162, "ETH-USD": 3400.0}.get(pair, 1.0)
            orchestrator.open_positions[pair] = {
                "entry_price": seed_price,
                "entry_cycle": 0,
                "entry_time": datetime.utcnow().isoformat(),
                "sentiment": 0.3,
                "regime": "SIDEWAYS",
                "size_mult": 1.0,
            }
            logger.info(f"[SMOKE TEST] Seeded {pair} @ ${seed_price}")

    for _ in range(cfg["total_cycles"]):
        try:
            cycle_start = time.time()
            orchestrator.run_cycle()
            elapsed = time.time() - cycle_start
            sleep_for = max(0, cfg["cycle_interval_seconds"] - elapsed)
            if sleep_for > 0 and orchestrator.cycle_count < cfg["total_cycles"]:
                time.sleep(sleep_for)
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
            break
        except Exception as e:
            logger.error(f"Fatal error at cycle {orchestrator.cycle_count}: {e}", exc_info=True)
            break

    orchestrator.print_summary()


if __name__ == "__main__":
    main()
