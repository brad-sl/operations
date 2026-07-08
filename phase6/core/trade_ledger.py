#!/usr/bin/env python3
"""
Phase 6 Trade Ledger
Persistent trade logging (JSONL + daily CSV)


See docs/DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py for paths and rules."""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, Optional


class TradeLedger:
    """Handles persistent trade logging for Phase 6."""

    def __init__(self, base_dir: Path = None):
        self.base_dir = base_dir or Path(__file__).parent.parent.parent
        self.trades_dir = self.base_dir / "trades"
        self.trades_dir.mkdir(parents=True, exist_ok=True)

        # Main JSONL log (append-only)
        self.jsonl_path = self.trades_dir / "phase6_trades.jsonl"

        # Dedicated influence stack snapshot log (for regime/X/Reddit time-series analysis)
        # Logged on trades + periodic snapshots (e.g. via report or runner)
        self.stack_log_path = self.base_dir / "data/state/influence_stack_log.jsonl"
        self.stack_log_path.parent.mkdir(parents=True, exist_ok=True)

        # Daily CSV (rotated) - basic fields; rich data lives in JSONL
        self.current_csv_date = None
        self.csv_path = None

    def _get_daily_csv_path(self) -> Path:
        """Get (or create) today's CSV file."""
        today = date.today().isoformat()
        if today != self.current_csv_date:
            self.current_csv_date = today
            self.csv_path = self.trades_dir / f"phase6_trades_{today}.csv"
            # Write header if new file
            if not self.csv_path.exists():
                header = "timestamp,pair,side,qty,entry_price,exit_price,pnl,pnl_pct,signal_source\n"
                self.csv_path.write_text(header)
        return self.csv_path

    def log_trade(self, trade: Dict[str, Any]) -> None:
        """
        Log a completed or attempted trade.
        Rich context (regime, influence_stack, x_sentiment etc.) is stored fully in JSONL for later analysis.
        CSV remains lightweight (basic fields + regime_bias column).
        """
        # Add timestamp if missing
        if "timestamp" not in trade:
            trade["timestamp"] = datetime.utcnow().isoformat()

        # Write full record (with possible influence_stack, regime, per-signal details) to JSONL
        with open(self.jsonl_path, "a") as f:
            f.write(json.dumps(trade) + "\n")

        # Write basic + regime to daily CSV for quick viewing
        csv_path = self._get_daily_csv_path()
        regime_bias = ""
        if "regime_bias" in trade:
            regime_bias = str(trade["regime_bias"])
        elif "influence_stack" in trade and isinstance(trade["influence_stack"], dict):
            pm = trade["influence_stack"].get("polymarket", {})
            regime_bias = str(pm.get("risk_on_bias", ""))

        # Ensure header has regime_bias column
        header = "timestamp,pair,side,qty,entry_price,exit_price,pnl,pnl_pct,signal_source,regime_bias\n"
        if not csv_path.exists():
            csv_path.write_text(header)
        else:
            existing = csv_path.read_text().splitlines()[0] if csv_path.read_text().strip() else ""
            if "regime_bias" not in existing:
                csv_path.write_text(header)

        line = (
            f"{trade.get('timestamp')},"
            f"{trade.get('pair')},"
            f"{trade.get('side')},"
            f"{trade.get('qty')},"
            f"{trade.get('entry_price')},"
            f"{trade.get('exit_price')},"
            f"{trade.get('pnl')},"
            f"{trade.get('pnl_pct')},"
            f"{trade.get('signal_source', 'unknown')},"
            f"{regime_bias}\n"
        )
        with open(csv_path, "a") as f:
            f.write(line)

    def log_decision_context(self, context: Dict[str, Any]) -> None:
        """
        Log rich decision context for measurement (tie-breaker / tilt analysis).
        Captures the moment of allocator / TradePlan decisions.

        Recommended fields:
          timestamp, decision_id (e.g. rebalance_ts),
          influence_stack (full snapshot or reference),
          x_strength, reddit_strength, pm_bias, pm_conf, pm_effective_influence,
          x_neutral, reddit_neutral, pm_used_as_tiebreaker (bool),
          other_factors (dict: price_trend, volume_spike, etc.),
          regime_mult_applied, baseline_plan (shadow without PM), tilted_plan,
          actions_taken
        """
        if "timestamp" not in context:
            context["timestamp"] = datetime.utcnow().isoformat() + "Z"

        context["type"] = "decision_context"
        context["source"] = "allocator_or_runner"

        # Append to the main trades JSONL (or a dedicated decisions log)
        decisions_path = self.base_dir / "data/state/decision_context_log.jsonl"
        decisions_path.parent.mkdir(parents=True, exist_ok=True)
        with open(decisions_path, "a") as f:
            f.write(json.dumps(context) + "\n")

        # Also attempt to attach key fields to the latest influence snapshot if possible
        try:
            if self.stack_log_path.exists():
                # lightweight marker on last snapshot (best-effort)
                pass
        except Exception:
            pass

        # Also emit to the regular influence stack log for time-series
        try:
            if "influence_stack" in context:
                self.log_influence_stack(context["influence_stack"])
        except Exception:
            pass

    def log_influence_stack(self, snapshot: Dict[str, Any]) -> None:
        """Append a full influence snapshot (called from report + decisions)."""
        with open(self.stack_log_path, "a") as f:
            f.write(json.dumps(snapshot) + "\n")

    def get_recent_trades(self, limit: int = 20) -> list:
        """Return the most recent trades from the JSONL file."""
        if not self.jsonl_path.exists():
            return []

        trades = []
        with open(self.jsonl_path, "r") as f:
            lines = f.readlines()[-limit:]
            for line in lines:
                try:
                    trades.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        return trades







    def log_influence_stack(self, snapshot):
        """Log full influence stack snapshot (X/Reddit/Polymarket) for 2-4 week impact analysis."""
        if "timestamp" not in snapshot:
            from datetime import datetime
            snapshot["timestamp"] = datetime.utcnow().isoformat() + "Z"
        with open(self.stack_log_path, "a") as f:
            f.write(__import__("json").dumps(snapshot) + "\n")

    def get_influence_stack_log(self, limit=None):
        """Return snapshots for analysis."""
        if not self.stack_log_path.exists():
            return []
        snaps = []
        with open(self.stack_log_path) as f:
            lines = f.readlines()
            if limit: lines = lines[-limit:]
            for line in lines:
                try:
                    snaps.append(__import__("json").loads(line.strip()))
                except: pass
        return snaps

    def analyze_regime_impact(self, min_trades=10):
        """Post 2-4wk analysis: bucket by regime_bias, compute win rates, relevance proxy."""
        import json
        trades = self.get_recent_trades(limit=10000)
        closed = [t for t in trades if t.get("pnl") is not None]
        if len(closed) < min_trades:
            return {"status": "insufficient_data", "closed_trades": len(closed)}
        buckets = {"high": [], "neutral": [], "low": []}
        for t in closed:
            rb = t.get("regime_bias")
            if rb is None and "influence_stack" in t:
                rb = t["influence_stack"].get("polymarket", {}).get("risk_on_bias")
            try:
                rb = float(rb) if rb is not None else 0.5
            except:
                rb = 0.5
            if rb > 0.65: buckets["high"].append(t)
            elif rb < 0.35: buckets["low"].append(t)
            else: buckets["neutral"].append(t)

        def stats(lst):
            if not lst: return {"n": 0}
            wins = sum(1 for x in lst if float(x.get("pnl",0)) > 0)
            tot = sum(float(x.get("pnl",0)) for x in lst)
            return {"n": len(lst), "win_rate": round(wins/len(lst),4), "total_pnl": round(tot,2)}

        base_wr = sum(1 for x in closed if float(x.get("pnl",0))>0) / len(closed) if closed else 0.5
        high_s = stats(buckets["high"])
        rel = 0.0
        if high_s["n"] > 0:
            lift = high_s["win_rate"] - base_wr
            rel = round(lift * (high_s["n"] / max(1,len(closed))) * 20, 4)
        return {
            "closed_trades": len(closed),
            "baseline_win_rate": round(base_wr,4),
            "high_risk_on": high_s,
            "neutral": stats(buckets["neutral"]),
            "risk_off": stats(buckets["low"]),
            "relevance_score": rel,
            "note": "Run after logging period. Positive relevance suggests regime adds edge."
        }


if __name__ == "__main__":
    # Quick test
    ledger = TradeLedger()
    test_trade = {
        "pair": "BTC-USD",
        "side": "BUY",
        "qty": 0.001,
        "entry_price": 65000.0,
        "exit_price": None,
        "pnl": 0,
        "pnl_pct": 0,
        "signal_source": "rsi"
    }
    ledger.log_trade(test_trade)
    print(f"Trade logged to {ledger.jsonl_path}")
    print("Recent trades:", ledger.get_recent_trades(5))
