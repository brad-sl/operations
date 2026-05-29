"""
Capital Allocation Engine Package - Phase 6.1 v1.1
Recurring job implementation for dynamic portfolio allocation and rebalancing.
"""

from .recurring_job import run_capital_allocation, load_config

__version__ = "1.1.0"
__all__ = ["run_capital_allocation", "load_config"]