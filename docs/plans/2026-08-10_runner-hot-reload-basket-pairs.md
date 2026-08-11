# Runner hot-reload basket pairs (no restart) Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** After `promote_basket_proposal.py` (or any edit to `global_settings.pairs`), the live Phase 6 runner picks up the new basket on the next cycle without process restart.

**Architecture:** Keep membership SSOT on disk (`config/trading_config_phase6.json` via `load_trading_basket()`). Each cycle, detect config mtime (or pairs fingerprint) change; if pairs differ from `runner.FIXED_UNIVERSE`, apply a **pairs-only** hot-swap: update in-memory universe + `config_dict` pairs, seed RSI/price history for **added** pairs, leave open inventory on **removed** pairs alone (membership ≠ liquidation). Do **not** full-reload all risk/capital knobs in v1 (avoid accidental mid-session thaw of SL/deploy/preserve).

**Tech Stack:** Python 3.11, existing `phase6.core.paths.load_trading_basket`, `Phase6Runner` main loop (~60s cycle), isolation tests under `scripts/phase6/` or `phase6/core/`.

---

## Current context / problem

| Fact | Detail |
|------|--------|
| Basket SSOT on disk | `load_trading_basket()` in `phase6/core/paths.py:179` reads `global_settings.pairs` every call |
| Runner cache | `Phase6Runner.__init__` sets `self.FIXED_UNIVERSE = self._load_full_universe(config_path)` **once** (`phase6_runner.py:131-194`) |
| Consumers | `cycle_coordinator`, `rebalance_coordinator`, RSI/price loop, sentiment load, dashboard seed all use `runner.FIXED_UNIVERSE` |
| Promote path | `scripts/phase6/promote_basket_proposal.py` writes config + metrics; **does not place orders**; currently needs runner restart for eligibility |
| Misleading docs | Promote print: “runner will treat new pairs as eligible on next cycle” — **false today** |
| Contrast | USDC park docs claim per-cycle config reload for that feature; **pairs do not** follow that path |

**Incident that motivated this:** 2026-08-11 OP→ICP promote required explicit runner restart so HybridRebalancer log showed `ICP-USD` in `global_settings.pairs`.

### Out of scope (v1)

- Hot-reload of full `trading_config_phase6.json` (deploy_pct, SL, preserve arm, capital_event_*, etc.)
- Auto-buy ICP / auto-sell OP on promote (membership-only remains correct)
- Sentiment cron / X spend changes (external jobs already call `load_trading_basket()` or their own lists — verify separately)
- Dashboard process restart (serve_dashboard already reads live_state; RSI tiles may lag until RSI merge for new pair)

### In scope (v1)

- Detect pairs list change
- Update `FIXED_UNIVERSE` + mirrored `config_dict["global_settings"]["pairs"]`
- Warm new pairs (price history + optional RSI seed)
- Drop removed pairs from **signal universe** only (not force-close)
- Isolation tests + promote/ops doc one-liners
- Structured log + optional state receipt for ops

---

## Proposed approach

### Design choice: mtime + pairs equality (recommended)

```
each _run_cycle start (or top of CycleCoordinator.run_cycle):
  path = runner.config_path or TRADING_CONFIG_PHASE6
  mtime = path.stat().st_mtime
  if mtime == runner._basket_config_mtime: return  # fast path
  new_pairs = load_trading_basket()  # or load from same path
  if new_pairs == runner.FIXED_UNIVERSE:
      runner._basket_config_mtime = mtime
      return
  apply_basket_hot_reload(runner, new_pairs, reason="config_mtime")
  runner._basket_config_mtime = mtime
```

**Why not full ConfigLoader reload every cycle?**  
Cheap mtime check is enough; full reload risks flipping unrelated live knobs and fighting in-memory capital/regime state. Pairs-only is YAGNI-correct for promote.

**Why not only a flag file?**  
Flag is a nice **optional accelerator** (`data/state/basket_reload.flag` touched by promote), but mtime alone is sufficient and can’t be forgotten if someone hand-edits config.

### Apply semantics

```text
old = set(FIXED_UNIVERSE)
new = list from disk (preserve order from config)
added   = [p for p in new if p not in old]
removed = [p for p in old if p not in new]

FIXED_UNIVERSE = new
config_dict["global_settings"]["pairs"] = new

for p in added:
  seed price_history (get_recent_prices limit=20)  # same as startup seed
  # optional: merge RSI via existing refresher helper if cheap; else next RSI cron/merge warms it
for p in removed:
  # do NOT cancel stops / sell
  # optional: leave rsi_values[p] in dict (harmless) or del if only used for basket signals
log [BASKET-RELOAD] added=… removed=… n=…
write data/state/basket_hot_reload_latest.json  # audit
```

### Sticky / safety guards (must keep)

| Guard | Behavior |
|-------|----------|
| Empty / short list | Refuse reload if `len(new) < 6` (or `< 8`) — log error, keep old |
| BTC/ETH missing | Refuse if sticky pairs absent from new list |
| Parse failure | Keep old universe; log once |
| Overlay | Do **not** re-apply full analyst overlays on pairs-only path |
| Concurrent promote mid-cycle | Next cycle retries; file write is atomic enough if promote uses write+replace (verify promote write pattern; if not, note follow-up) |

### Where to hook

**Preferred single call site:** start of `CycleCoordinator.run_cycle` **or** first lines of `Phase6Runner._run_cycle` before capital events / rebalance — so every ~60s path sees new basket before evaluation.

```python
# phase6_runner.py _run_cycle
def _run_cycle(self, cycle_num: int):
    self.maybe_reload_trading_basket()
    self._cycle_coordinator.run_cycle(self, cycle_num, ...)
```

Implement `maybe_reload_trading_basket` on runner (or small module `phase6/core/basket_hot_reload.py` for testability).

### Deduplicate loaders

Replace `_load_full_universe` body with:

```python
def _load_full_universe(self, config_path: str):
    # Prefer paths.load_trading_basket when path is default;
    # if custom config_path (tests), load pairs from that file only.
    ...
```

Avoid two diverging fallbacks (paths.py still lists ADA/OP in fallback — update fallback to current-style basket or “last known” only in tests).

### Promote script touch-up

After successful config write:

```python
# optional
flag = STATE_DIR / "basket_reload.flag"
flag.write_text(datetime.now(timezone.utc).isoformat())
```

Runner: if flag exists, force reload even if mtime clock resolution is coarse, then unlink flag.

Update promote stdout: “Hot-reload within ~60s if runner supports basket_hot_reload; restart only if log lacks [BASKET-RELOAD].”

### Docs / skills

- `phase6-pair-discovery` SKILL + `references/promote-and-metrics.md`: drop “must restart runner” for pairs-only; say verify `[BASKET-RELOAD]` in log.
- `references/phase6-runner-restart.md`: restart still required for **code** deploys and non-pairs config that isn’t hot-reloaded.

---

## Step-by-step tasks

### Task 1: Isolation test skeleton (failing)

**Objective:** Lock desired API before implementation.

**Files:**
- Create: `scripts/phase6/test_isolation_basket_hot_reload.py`

**Step 1: Write failing test**

```python
"""Isolation: basket hot-reload updates FIXED_UNIVERSE without full runner restart."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

# Import will fail until module exists
from phase6.core.basket_hot_reload import apply_basket_hot_reload, pairs_changed


def test_pairs_changed_detects_swap():
    assert pairs_changed(
        ["BTC-USD", "ETH-USD", "OP-USD"],
        ["BTC-USD", "ETH-USD", "ICP-USD"],
    )
    assert not pairs_changed(["A", "B"], ["A", "B"])


def test_apply_updates_universe_and_config_dict():
    runner = SimpleNamespace(
        FIXED_UNIVERSE=["BTC-USD", "ETH-USD", "OP-USD"],
        config_dict={"global_settings": {"pairs": ["BTC-USD", "ETH-USD", "OP-USD"]}},
        price_history=MagicMock(),
        exchange=MagicMock(),
        rsi_values={},
    )
    runner.exchange.get_recent_prices.return_value = [1.0] * 20

    result = apply_basket_hot_reload(
        runner,
        ["BTC-USD", "ETH-USD", "ICP-USD"],
        reason="test",
        seed_prices=True,
    )
    assert runner.FIXED_UNIVERSE == ["BTC-USD", "ETH-USD", "ICP-USD"]
    assert runner.config_dict["global_settings"]["pairs"] == runner.FIXED_UNIVERSE
    assert result["added"] == ["ICP-USD"]
    assert result["removed"] == ["OP-USD"]
    assert runner.exchange.get_recent_prices.called


def test_refuse_empty_or_missing_sticky():
    runner = SimpleNamespace(
        FIXED_UNIVERSE=["BTC-USD", "ETH-USD", "OP-USD"],
        config_dict={"global_settings": {"pairs": ["BTC-USD", "ETH-USD", "OP-USD"]}},
        price_history=MagicMock(),
        exchange=MagicMock(),
        rsi_values={},
    )
    r1 = apply_basket_hot_reload(runner, [], reason="test")
    assert r1.get("ok") is False
    assert runner.FIXED_UNIVERSE[0] == "BTC-USD"
    r2 = apply_basket_hot_reload(runner, ["SOL-USD", "ICP-USD"], reason="test")  # no BTC/ETH
    assert r2.get("ok") is False


if __name__ == "__main__":
    test_pairs_changed_detects_swap()
    test_apply_updates_universe_and_config_dict()
    test_refuse_empty_or_missing_sticky()
    print("PASS")
```

**Step 2: Run**

```bash
cd /home/brad/projects/crypto-trading-bot
export OPENBLAS_CORETYPE=GENERIC
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_basket_hot_reload.py
```

Expected: FAIL — `ModuleNotFoundError: basket_hot_reload`

---

### Task 2: Implement `basket_hot_reload` module

**Objective:** Pure helper with apply + maybe_reload.

**Files:**
- Create: `phase6/core/basket_hot_reload.py`

**Minimal API:**

```python
# phase6/core/basket_hot_reload.py
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from phase6.core.paths import PROJECT_ROOT, STATE_DIR, TRADING_CONFIG_PHASE6, load_trading_basket

logger = logging.getLogger("phase6.basket_hot_reload")

STICKY = ("BTC-USD", "ETH-USD")
MIN_PAIRS = 6
RELOAD_FLAG = STATE_DIR / "basket_reload.flag"
RECEIPT = STATE_DIR / "basket_hot_reload_latest.json"


def pairs_changed(old: Sequence[str], new: Sequence[str]) -> bool:
    return list(old) != list(new)


def apply_basket_hot_reload(
    runner: Any,
    new_pairs: Sequence[str],
    *,
    reason: str = "unspecified",
    seed_prices: bool = True,
    sticky: Sequence[str] = STICKY,
    min_pairs: int = MIN_PAIRS,
) -> Dict[str, Any]:
    new_list = [str(p).strip() for p in new_pairs if str(p).strip()]
    old_list = list(getattr(runner, "FIXED_UNIVERSE", []) or [])
    if len(new_list) < min_pairs:
        logger.error("[BASKET-RELOAD] refuse short list n=%s reason=%s", len(new_list), reason)
        return {"ok": False, "error": "too_short", "n": len(new_list)}
    for s in sticky:
        if s not in new_list:
            logger.error("[BASKET-RELOAD] refuse missing sticky %s reason=%s", s, reason)
            return {"ok": False, "error": "missing_sticky", "pair": s}
    if not pairs_changed(old_list, new_list):
        return {"ok": True, "changed": False, "pairs": new_list}

    old_set, new_set = set(old_list), set(new_list)
    added = [p for p in new_list if p not in old_set]
    removed = [p for p in old_list if p not in new_set]

    runner.FIXED_UNIVERSE = list(new_list)
    cfg = getattr(runner, "config_dict", None)
    if isinstance(cfg, dict):
        gs = cfg.setdefault("global_settings", {})
        if isinstance(gs, dict):
            gs["pairs"] = list(new_list)

    seeded = []
    if seed_prices:
        ex = getattr(runner, "exchange", None)
        ph = getattr(runner, "price_history", None)
        for p in added:
            try:
                if ex is None or ph is None:
                    break
                recent = ex.get_recent_prices(p, limit=20)
                if recent:
                    for price in recent:
                        ph.add_price(p, price)
                    seeded.append(p)
            except Exception as e:
                logger.warning("[BASKET-RELOAD] seed failed %s: %s", p, e)

    receipt = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ok": True,
        "changed": True,
        "reason": reason,
        "before": old_list,
        "after": list(new_list),
        "added": added,
        "removed": removed,
        "seeded": seeded,
    }
    try:
        RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        RECEIPT.write_text(json.dumps(receipt, indent=2))
    except Exception as e:
        logger.debug("receipt write: %s", e)

    logger.info(
        "[BASKET-RELOAD] %s -> added=%s removed=%s n=%s reason=%s",
        old_list,
        added,
        removed,
        len(new_list),
        reason,
    )
    return receipt


def maybe_reload_trading_basket(runner: Any, config_path: Optional[str | Path] = None) -> Dict[str, Any]:
    """No-op if mtime unchanged and no flag; else load pairs and apply."""
    path = Path(config_path or getattr(runner, "config_path", None) or TRADING_CONFIG_PHASE6)
    force = RELOAD_FLAG.exists()
    try:
        mtime = path.stat().st_mtime
    except OSError as e:
        logger.warning("[BASKET-RELOAD] stat failed: %s", e)
        return {"ok": False, "error": "stat"}

    last = getattr(runner, "_basket_config_mtime", None)
    if not force and last is not None and mtime == last:
        return {"ok": True, "changed": False, "skipped": "mtime"}

    # Load pairs: default SSOT vs custom path for tests
    if path.resolve() == Path(TRADING_CONFIG_PHASE6).resolve():
        new_pairs = load_trading_basket()
    else:
        cfg = json.loads(path.read_text())
        new_pairs = list((cfg.get("global_settings") or {}).get("pairs") or [])

    reason = "flag" if force else "config_mtime"
    result = apply_basket_hot_reload(runner, new_pairs, reason=reason, seed_prices=True)
    runner._basket_config_mtime = mtime
    if force:
        try:
            RELOAD_FLAG.unlink(missing_ok=True)
        except TypeError:
            if RELOAD_FLAG.exists():
                RELOAD_FLAG.unlink()
    return result
```

**Step 3: Re-run isolation** — expect PASS.

---

### Task 3: Wire into runner

**Objective:** Call reload every cycle; init mtime; store `config_path`.

**Files:**
- Modify: `phase6/core/phase6_runner.py`

**Changes:**
1. In `__init__` after setting `FIXED_UNIVERSE`:
   - `self.config_path = config_path`
   - `self._basket_config_mtime = None` then set from `Path(config_path).stat().st_mtime` if exists
2. Prefer `_load_full_universe` → delegate to `load_trading_basket` when path is default
3. In `_run_cycle` **first line**:

```python
def _run_cycle(self, cycle_num: int):
    try:
        from phase6.core.basket_hot_reload import maybe_reload_trading_basket
        maybe_reload_trading_basket(self, getattr(self, "config_path", None))
    except Exception as e:
        logger.warning("[BASKET-RELOAD] cycle hook failed: %s", e)
    self._cycle_coordinator.run_cycle(...)
```

**Do not** put heavy work in the 60s sleep path outside `_run_cycle`.

---

### Task 4: Promote script flag + message

**Objective:** Promote path triggers immediate next-cycle reload.

**Files:**
- Modify: `scripts/phase6/promote_basket_proposal.py` (after successful config write)

```python
from phase6.core.paths import STATE_DIR  # or basket_hot_reload.RELOAD_FLAG
flag = STATE_DIR / "basket_reload.flag"
flag.write_text(datetime.now(timezone.utc).isoformat() + "\n")
print("Touched basket_reload.flag — live runner should log [BASKET-RELOAD] within ~60s (no restart).")
```

---

### Task 5: Fix hardcoded stale fallbacks (light)

**Objective:** Avoid OP/ADA frozen fallbacks lying after hot-reload tests.

**Files:**
- Modify: `phase6/core/paths.py` fallback list comment + align with “BTC/ETH + 9 slots” or document as legacy-only
- `hybrid_rebalancer.py` `__main__` smoke universe: call `load_trading_basket()` instead of hardcoded OP list

---

### Task 6: Docs / skill one-liners

**Files:**
- `~/.hermes/skills/trading-bot-operations/phase6-pair-discovery/SKILL.md` (Live promote section)
- `.../references/promote-and-metrics.md`
- Optional project: `docs/BASKET_HOT_RELOAD.md` (short operator note)

**Text:**

```markdown
## Runner pickup
Promote writes config + `data/state/basket_reload.flag`.
Live runner hot-reloads `global_settings.pairs` each cycle (`[BASKET-RELOAD]` log).
**Restart not required** for pairs-only membership changes.
Still restart for runner **code** deploys or non-pairs config that is not hot-reloaded.
Verify: `rg BASKET-RELOAD logs/phase6_runner.log | tail`
```

---

### Task 7: Live verification (staging-safe)

**Objective:** Prove on running system without bad promote.

**Steps:**
1. Deploy code + **one** runner restart (code deploy — last restart for this feature).
2. Dry-run: touch flag only → log should show skip or no-op if pairs unchanged.
3. Optional: temporary dry promote in shadow mode OR edit a **copy** config in unit test only — do not thrash live basket in prod verify.
4. Next real promote: confirm `[BASKET-RELOAD] ... added=['ICP-USD']` style line within 60–120s **without** restart.

```bash
rg "BASKET-RELOAD" logs/phase6_runner.log | tail -5
cat data/state/basket_hot_reload_latest.json
pgrep -af phase6.core.phase6_runner   # same PID as before promote
```

---

## Files likely to change

| Path | Role |
|------|------|
| `phase6/core/basket_hot_reload.py` | **Create** — core logic |
| `phase6/core/phase6_runner.py` | Hook + config_path + mtime |
| `scripts/phase6/test_isolation_basket_hot_reload.py` | **Create** — isolation |
| `scripts/phase6/promote_basket_proposal.py` | Flag + message |
| `phase6/core/paths.py` | Optional fallback cleanup |
| `phase6/core/rebalancing/hybrid_rebalancer.py` | Smoke list only |
| pair-discovery skill + promote ref | Ops truth |
| `docs/BASKET_HOT_RELOAD.md` | Optional short runbook |

---

## Tests / validation

| Test | Command | Pass criteria |
|------|---------|---------------|
| Isolation | `PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_basket_hot_reload.py` | prints PASS |
| Existing paper chain (smoke) | `phase6/tests/test_full_paper_trade_chain.py` if still green in env | basket len still matches |
| Live | promote or flag + `rg BASKET-RELOAD` | log + receipt; **PID unchanged** |
| Negative | empty pairs file in unit test | refuse; old universe kept |

---

## Risks, tradeoffs, open questions

| Risk | Mitigation |
|------|------------|
| Mid-cycle basket change during rebalance | Reload at **start** of cycle only; rebalance uses post-reload universe consistently |
| New pair missing RSI → bad entries | Seed prices; entry gates still RSI/sentiment; RSI cron merge for new pair within hours; optional inline `--merge` warm for added only (nice-to-have Task 3b) |
| Removed pair still held | **Correct** — membership only; protect threshold already on promote |
| mtime coarse on some FS | Flag from promote |
| Full config hot-reload creep | Explicitly out of scope; document |
| `opportunity_pool` still lists OP after promote | Cosmetic; optional promote also appends add to opportunity_pool (follow-up, not blocker) |
| Analyst overlay pairs? | Overlays today don’t own basket membership — ignore |

**Open questions for Brad (defaults chosen):**
1. Inline RSI warm for added pairs on reload? **Default yes if <3 adds and exchange OK; skip if slow.**
2. Min basket size 6 vs 8 vs 11? **Default 6 with sticky BTC/ETH.**
3. Should hand-edit of config without flag reload? **Yes via mtime.**

---

## Implementation order (summary)

1. Failing isolation test  
2. `basket_hot_reload.py`  
3. Wire `_run_cycle`  
4. Promote flag + log message  
5. Docs/skill  
6. Deploy runner **once** for code  
7. Verify next promote without restart  

---

## Success criteria

- [ ] Promote OP→ICP class swap: config written, **same runner PID**, log `[BASKET-RELOAD]` within ~2 cycles  
- [ ] New pair appears in rebalance/sentiment universe (`runner.FIXED_UNIVERSE`)  
- [ ] Removed pair not in signal basket; any residual inventory untouched  
- [ ] Isolation PASS; no orders from reload path  
- [ ] Ops docs no longer require restart for pairs-only  

---

## Commit plan

```bash
git add phase6/core/basket_hot_reload.py scripts/phase6/test_isolation_basket_hot_reload.py
git commit -m "feat(phase6): isolation + basket hot-reload helper"

git add phase6/core/phase6_runner.py scripts/phase6/promote_basket_proposal.py
git commit -m "feat(phase6): reload trading basket each cycle without restart"

git add docs/BASKET_HOT_RELOAD.md  # if added
# skill patch via skill_manage
git commit -m "docs: basket hot-reload ops note"
```
