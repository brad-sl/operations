"""Phase 6 action domain — ports inward, receipts outward.

New product behavior lands here (or domain/services + domain/actions).
Legacy phase6/core shrinks; bridge only.
"""

from phase6.domain.types import ActionName, ActionReceipt, ActionRequest

__all__ = ["ActionName", "ActionReceipt", "ActionRequest"]
