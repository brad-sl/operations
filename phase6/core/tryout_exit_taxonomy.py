"""Tryout / bag exit taxonomy — single map from ledger reasons → closed class.

SSOT for process-tax scoreboards, dwell stages, and decision-discipline outcomes.
Does not place orders. Prefer this over ad-hoc string matching in callers.

Classes (TRYOUT_LIFECYCLE_PROCESS.md):
  CLOSED_SL, CLOSED_TP_TRAIL, CLOSED_DUAL_PEAK, CLOSED_SCALE_WINDOW,
  CLOSED_OPERATOR, CLOSED_DUST, CLOSED_OTHER
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

SCHEMA = "tryout_exit_taxonomy_v1"

# Canonical closed classes (product)
CLOSED_SL = "CLOSED_SL"
CLOSED_TP_TRAIL = "CLOSED_TP_TRAIL"
CLOSED_DUAL_PEAK = "CLOSED_DUAL_PEAK"
CLOSED_SCALE_WINDOW = "CLOSED_SCALE_WINDOW"
CLOSED_OPERATOR = "CLOSED_OPERATOR"
CLOSED_DUST = "CLOSED_DUST"
CLOSED_OTHER = "CLOSED_OTHER"

# Dwell stage ids (pair_funnel_dwell terminal stages)
DWELL_EXIT_SL = "exit_sl"
DWELL_EXIT_TP = "exit_tp"
DWELL_EXIT_SCALE_WINDOW = "exit_scale_window"
DWELL_EXIT_OTHER = "exit_other"

# Attribution weekly buckets (compat)
ATTR_SL = "sl_exchange"
ATTR_TP = "tp_profit"
ATTR_DUAL = "dual_peak"
ATTR_DUST = "dust_sweep"
ATTR_HARD = "hard_exit"
ATTR_ROT = "rotation"
ATTR_OP = "operator_manual"
ATTR_SCALE = "scale_window_eject"
ATTR_OTHER = "other"
ATTR_BLANK = "blank_untagged"


def _reason_text(row_or_reason: Any) -> str:
    if row_or_reason is None:
        return ""
    if isinstance(row_or_reason, Mapping):
        return str(
            row_or_reason.get("reason")
            or row_or_reason.get("exit_reason")
            or row_or_reason.get("done_reason")
            or row_or_reason.get("signal_source")
            or ""
        ).strip()
    return str(row_or_reason or "").strip()


def classify_closed_class(row_or_reason: Any) -> str:
    """Map any exit reason / ledger row → CLOSED_* class."""
    reason = _reason_text(row_or_reason)
    r = reason.lower()
    if not r:
        return CLOSED_OTHER

    if "tryout_scale_window" in r or "scale_window_eject" in r:
        return CLOSED_SCALE_WINDOW

    if "dust_sweep" in r or r.startswith("dust"):
        return CLOSED_DUST

    if any(
        k in r
        for k in (
            "stop_loss",
            "stop-loss",
            "exchange_stop",
            "sl_hit",
            "sl_",
            "_sl",
            "stop_loss_exchange",
            "missfire",
            "hard_exit",
            "liquidation",
            "regime_hard_exit",
        )
    ):
        # hard_exit is process wound class → SL family for tax boards
        return CLOSED_SL

    if "dual_peak" in r or "lifecycle_dual_peak" in r:
        return CLOSED_DUAL_PEAK

    if any(
        k in r
        for k in (
            "take_profit",
            "fixed_tp",
            "trail",
            "tp_",
            "lifecycle_extension",
            "extension_partial",
        )
    ):
        return CLOSED_TP_TRAIL

    if any(
        k in r
        for k in (
            "operator",
            "manual",
            "preserve_disarm",
            "operator_trim",
            "operator_unwind",
            "manual_liquidation",
        )
    ):
        return CLOSED_OPERATOR

    if "rotation" in r:
        # rotation is not tryout-shell default; still not SL tax
        return CLOSED_OTHER

    if "test_cleanup" in r or "cleanup" in r:
        return CLOSED_OPERATOR

    return CLOSED_OTHER


def closed_class_to_dwell_stage(closed_class: str) -> str:
    cc = str(closed_class or CLOSED_OTHER)
    if cc == CLOSED_SL:
        return DWELL_EXIT_SL
    if cc in (CLOSED_TP_TRAIL, CLOSED_DUAL_PEAK):
        return DWELL_EXIT_TP
    if cc == CLOSED_SCALE_WINDOW:
        return DWELL_EXIT_SCALE_WINDOW
    return DWELL_EXIT_OTHER


def closed_class_to_attr_bucket(closed_class: str) -> str:
    cc = str(closed_class or CLOSED_OTHER)
    return {
        CLOSED_SL: ATTR_SL,
        CLOSED_TP_TRAIL: ATTR_TP,
        CLOSED_DUAL_PEAK: ATTR_DUAL,
        CLOSED_SCALE_WINDOW: ATTR_SCALE,
        CLOSED_OPERATOR: ATTR_OP,
        CLOSED_DUST: ATTR_DUST,
        CLOSED_OTHER: ATTR_OTHER,
    }.get(cc, ATTR_OTHER)


def closed_class_to_outcome(closed_class: str) -> str:
    """Decision-discipline outcome_class labels."""
    cc = str(closed_class or CLOSED_OTHER)
    if cc == CLOSED_SL:
        return "sl"
    if cc == CLOSED_TP_TRAIL:
        return "tp"
    if cc == CLOSED_DUAL_PEAK:
        return "dual_peak"
    if cc == CLOSED_SCALE_WINDOW:
        return "scale_window"
    if cc == CLOSED_OPERATOR:
        return "operator"
    if cc == CLOSED_DUST:
        return "dust"
    return "other"


def is_process_tax_class(closed_class: str) -> bool:
    return str(closed_class) in {CLOSED_SL, CLOSED_DUST}


def stamp_exit_taxonomy(trade: Dict[str, Any]) -> Dict[str, Any]:
    """Mutate-copy: add exit_class fields on SELL rows."""
    out = dict(trade)
    side = str(out.get("side") or out.get("action") or "").upper()
    if side != "SELL":
        return out
    cc = classify_closed_class(out)
    out["exit_class"] = cc
    out["exit_taxonomy_schema"] = SCHEMA
    out["exit_dwell_stage"] = closed_class_to_dwell_stage(cc)
    out["exit_attr_bucket"] = closed_class_to_attr_bucket(cc)
    out["exit_outcome_class"] = closed_class_to_outcome(cc)
    out["exit_process_tax"] = is_process_tax_class(cc)
    return out


def classify_exit_reason_attr(row: Mapping[str, Any]) -> str:
    """Drop-in for attribution_rt_weekly.classify_exit_reason."""
    reason = _reason_text(row)
    if not reason:
        return ATTR_BLANK
    return closed_class_to_attr_bucket(classify_closed_class(row))
