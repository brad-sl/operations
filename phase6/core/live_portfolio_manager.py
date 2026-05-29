"""
Stub for LivePortfolioManager to allow initialization during migration.
"""

class LivePortfolioManager:
    def __init__(self, exchange, initial_capital=1000.0):
        self.exchange = exchange
        self.initial_capital = initial_capital
        self.positions = {}

    def has_open_positions(self):
        return len(self.positions) > 0

    def get_positions(self):
        return self.positions
