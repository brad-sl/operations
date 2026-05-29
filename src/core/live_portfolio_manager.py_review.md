============================================================
CODE REVIEW REPORT
============================================================

## analysis
{
  "issues": [
    {
      "title": "Position / RiskLimits classes cannot be instantiated as intended",
      "details": "The snippet defines `Position` and `RiskLimits` with only annotated attributes but never decorates them with `@dataclass` or implements an `__init__`. Any code that tries to create `Position(pair, qty, entry_price)` (as suggested in the docstring) will raise `TypeError: Position() takes no arguments`. Furthermore, since the attributes are class variables, every instance shares defaults unless manually assigned, so serialisation/deserialisation logic will break.",
      "root_cause": "The file imports `dataclass` but never applies it to these helper classes, so they remain plain classes with no constructor or automatic `asdict` support.",
      "impact": "Live trading logic that creates `Position` objects for reconciliation, risk calculations, or persistence will crash immediately at runtime. This stops the bot from starting and prevents risk rules from executing.",
      "fix": "Turn these helpers into proper dataclasses so that they can be instantiated and serialised safely.",
      "code_changes": [
        "```python\nfrom dataclasses import dataclass\n\n@dataclass\nclass Position:\n    pair: str\n    qty: float\n    entry_price: float\n    current_price: float = 0.0\n    unrealized_pnl: float = 0.0\n    sl_price: float = 0.0\n    tp_price: float = 0.0\n\n@dataclass\nclass RiskLimits:\n    max_daily_loss_pct: float = 0.05\n    max_trade_pct: float = 0.01\n```"
      ],
      "tests": [
        "Instantiate `Position` with all required args and ensure attributes round-trip via `asdict()`.",
        "Instantiate `RiskLimits` and check defaults (e.g. `max_daily_loss_pct == 0.05`)."
      ]
    },
    {
      "title": "Crash recovery swallows startup failures leading to silent halt",
      "details": "`crash_recovery` simply calls `self.reconcile_positions()` and logs success. If `reconcile_positions` fails (e.g. network outage, DB locked), the exception propagates and the process exits without retrying, logging, or resetting state. There's no guardrail, so a transient Coinbase outage prevents the bot from restarting.",
      "root_cause": "No try/except or recovery mechanism around the critical `reconcile_positions` step during crash recovery.",
      "impact": "Live trading systems relying on crash recovery will not start after a temporary failure and operators may have to manually intervene without any diagnostic in logs.",
      "fix": "Wrap the reconciliation in a try/

