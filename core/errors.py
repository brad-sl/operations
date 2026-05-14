class CryptoBotError(Exception):
    """Base exception for crypto bot errors."""

class APIError(CryptoBotError):
    """Base for API-related errors."""

class OrderFailed(APIError):
    """Order placement failed."""

class APITimeout(APIError):
    """API request timed out."""

class InsufficientBalance(CryptoBotError):
    """Not enough balance for trade."""

class InvalidSignal(CryptoBotError):
    """Signal validation failed."""

class DatabaseError(CryptoBotError):
    """Database operation failed."""
