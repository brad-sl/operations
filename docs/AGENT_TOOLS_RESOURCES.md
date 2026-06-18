# Agent Tools & Resources Guide

This document lists persistent data sources, logs, and tools that all agents should be aware of when starting work on the crypto trading bot.

## 1. Trade Activity Log

**Location**: `data/state/trade_activity.jsonl`

**Purpose**: Append-only log of all trading activity (trades, rebalances, stop-loss triggers, position updates).

**Format**: JSON Lines (one JSON object per line)

**Key Fields**:
- `timestamp`
- `event_type` (trade, rebalance, stop_loss, position_update)
- `pair`
- `side` (buy / sell)
- `qty`
- `price`
- `usd_value`
- `pnl`
- `source`

**Usage**:
- Agents should read this file when they need recent trading history.
- The runner (`phase6_runner.py`) is responsible for writing to this log.

## 2. Live State Cache

**Location**: `data/state/phase6_live_state.json`

**Purpose**: Current snapshot of balances, positions, and portfolio value written by the runner every cycle.

**Key Fields**:
- `balances[]`
- `positions[]`
- `total_usd`
- `last_updated`

## 3. Trade Ledger

**Location**: `phase6/core/trade_ledger.py` (class)

**Purpose**: Structured access to trade history via `get_recent_trades()` and related methods.

## 4. Stop-Loss State

Managed by `StopLossCoordinator` and `StopLossManager` in `phase6/core/`.

## How to Use This Guide

All agents should read this document at the start of a new task so they know what data sources are available without having to rediscover them.

This file should be kept up to date whenever new persistent data sources or tools are added.