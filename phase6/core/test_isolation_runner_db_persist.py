import sqlite3
import unittest
import os
import shutil
from pathlib import Path
from phase6.core.phase6_runner import Phase6Runner

class TestRunnerDBPersistence(unittest.TestCase):
    def setUp(self):
        self.db_path = "/home/brad/projects/crypto-trading-bot/data/phase6.db"
        
    def test_persist_facts(self):
        runner = Phase6Runner(config_path="projects/crypto-trading-bot/configs/trading_config_phase6.json", mode="shadow")
        
        # Test persist_facts_to_db call
        test_ts = "2026-06-12T12:00:00"
        facts = {
            "balances": [{"ts": test_ts, "currency": "USD", "balance": 1000.0}],
            "holdings": [{"ts": test_ts, "currency": "ETH", "amount": 0.5}],
            "prices": [{"ts": test_ts, "pair": "ETH-USD", "price": 3000.0}],
            "rsi": [{"ts": test_ts, "pair": "ETH-USD", "value": 45.0}],
            "sentiment": [{"ts": test_ts, "pair": "ETH-USD", "score": 0.8}]
        }
        
        runner.persist_facts_to_db(facts)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT balance FROM account_balances WHERE currency='USD'")
        self.assertEqual(cursor.fetchone()[0], 1000.0)
        
        cursor.execute("SELECT amount FROM holdings WHERE currency='ETH'")
        self.assertEqual(cursor.fetchone()[0], 0.5)
        
        conn.close()

if __name__ == "__main__":
    unittest.main()
