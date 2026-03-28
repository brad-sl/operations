"""
SEO Agent Database Manager

Handles all database operations for client tracking, KPI monitoring,
and reporting for the SEO Agent skill.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path


class SEODatabase:
    """Database manager for SEO Agent client tracking and reporting."""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path(__file__).parent / "seo_tracking.db"
        self.db_path = str(db_path)
        self._init_db()
    
    def _init_db(self):
        """Initialize database with schema."""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path, 'r') as f:
            schema = f.read()
        
        conn = sqlite3.connect(self.db_path)
        conn.executescript(schema)
        conn.commit()
        conn.close()
    
    def _query(self, sql: str, params: tuple = None, fetch: str = 'all'):
        """Execute a query and return results."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        
        if fetch == 'all':
            result = [dict(row) for row in cursor.fetchall()]
        elif fetch == 'one':
            row = cursor.fetchone()
            result = dict(row) if row else None
        elif fetch == 'last_id':
            result = cursor.lastrowid
        else:
            result = None
        
        conn.commit()
        conn.close()
        return result
    
    # =======================
    # CLIENT OPERATIONS
    # =======================
    
    def add_client(self, domain: str, business_name: str, business_model: str) -> int:
        """Register a new client."""
        return self._query(
            """INSERT INTO clients (domain, business_name, business_model) 
               VALUES (?, ?, ?)""",
            (domain, business_name, business_model),
            fetch='last_id'
        )
    
    def get_client(self, domain: str = None, client_id: int = None) -> dict:
        """Get client by domain or ID."""
        if domain:
            return self._query(
                "SELECT * FROM clients WHERE domain = ?",
                (domain,),
                fetch='one'
            )
        elif client_id:
            return self._query(
                "SELECT * FROM clients WHERE client_id = ?",
                (client_id,),
                fetch='one'
            )
        return None
    
    def list_clients(self, status: str = 'active') -> list:
        """List all clients, optionally filtered by status."""
        return self._query(
            "SELECT * FROM clients WHERE status = ? ORDER BY created_at DESC",
            (status,)
        )
    
    def update_client_audit(self, client_id: int):
        """Update last_audit timestamp for client."""
        self._query(
            "UPDATE clients SET last_audit = ? WHERE client_id = ?",
            (datetime.now().isoformat(), client_id)
        )
    
    # =======================
    # KPI OPERATIONS
    # =======================
    
    def record_monthly_kpis(self, client_id: int, month: str, 
                           traffic: int = None, avg_rank: float = None,
                           keywords: int = None, pages: int = None,
                           backlinks: int = None, conversions: int = None) -> int:
        """Record monthly KPI snapshot."""
        return self._query(
            """INSERT OR REPLACE INTO monthly_kpis 
               (client_id, report_month, organic_traffic, avg_ranking, 
                total_keywords_ranking, indexed_pages, backlinks, organic_conversions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (client_id, month, traffic, avg_rank, keywords, pages, backlinks, conversions),
            fetch='last_id'
        )
    
    def get_kpi_trend(self, client_id: int, months: int = 6) -> list:
        """Get KPI trend for last N months."""
        return self._query(
            """SELECT * FROM monthly_kpis 
               WHERE client_id = ? 
               ORDER BY report_month DESC 
               LIMIT ?""",
            (client_id, months)
        )
    
    def calculate_position_changes(self, client_id: int) -> dict:
        """Calculate keyword position gains/losses."""
        gains = self._query(
            """SELECT COUNT(*) as count FROM keyword_rankings 
               WHERE client_id = ? AND change_direction = 'up'""",
            (client_id,)
        )
        losses = self._query(
            """SELECT COUNT(*) as count FROM keyword_rankings 
               WHERE client_id = ? AND change_direction = 'down'""",
            (client_id,)
        )
        return {
            'keywords_gained': gains[0]['count'] if gains else 0,
            'keywords_lost': losses[0]['count'] if losses else 0
        }
    
    # =======================
    # KEYWORD OPERATIONS
    # =======================
    
    def track_keyword(self, client_id: int, keyword: str, volume: int = None,
                     difficulty: float = None, intent: str = None,
                     current_rank: int = None) -> int:
        """Add or update keyword tracking."""
        existing = self._query(
            "SELECT current_rank FROM keyword_rankings WHERE client_id = ? AND keyword = ?",
            (client_id, keyword),
            fetch='one'
        )
        
        if existing:
            # Update existing keyword
            prev_rank = existing.get('current_rank')
            if current_rank and prev_rank:
                change = prev_rank - current_rank  # Positive = improved (lower is better)
                direction = 'up' if change > 0 else ('down' if change < 0 else 'stable')
            else:
                direction = 'stable'
                change = 0
            
            self._query(
                """UPDATE keyword_rankings SET 
                   current_rank = ?, previous_rank = COALESCE(?, current_rank),
                   change_direction = ?, position_change = ?,
                   last_checked = ?
                   WHERE client_id = ? AND keyword = ?""",
                (current_rank, prev_rank, direction, change, 
                 datetime.now().isoformat(), client_id, keyword)
            )
            
            # Add to history
            ranking_id = self._query(
                "SELECT ranking_id FROM keyword_rankings WHERE client_id = ? AND keyword = ?",
                (client_id, keyword),
                fetch='one'
            )
            if ranking_id:
                self._query(
                    "INSERT INTO keyword_history (ranking_id, rank_position, checked_date) VALUES (?, ?, ?)",
                    (ranking_id['ranking_id'], current_rank, datetime.now().isoformat())
                )
        else:
            # Insert new keyword
            return self._query(
                """INSERT INTO keyword_rankings 
                   (client_id, keyword, search_volume, difficulty, intent, current_rank, tracked_since)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (client_id, keyword, volume, difficulty, intent, current_rank, datetime.now().isoformat()),
                fetch='last_id'
            )
    
    def get_keyword_rankings(self, client_id: int, limit: int = 50) -> list:
        """Get all tracked keywords for a client."""
        return self._query(
            """SELECT * FROM keyword_rankings 
               WHERE client_id = ? 
               ORDER BY current_rank ASC 
               LIMIT ?""",
            (client_id, limit)
        )
    
    # =======================
    # AUDIT LOGGING
    # =======================
    
    def log_audit(self, client_id: int, prompt_id: str, prompt_name: str,
                  status: str = 'completed', findings: int = 0,
                  recommendations: int = 0, duration: float = None,
                  report_path: str = None) -> int:
        """Log audit execution."""
        return self._query(
            """INSERT INTO audit_logs 
               (client_id, prompt_id, prompt_name, status, findings_count, 
                recommendations_count, execution_time_seconds, report_file_path, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (client_id, prompt_id, prompt_name, status, findings, recommendations,
             duration, report_path, datetime.now().isoformat()),
            fetch='last_id'
        )
    
    def get_audit_history(self, client_id: int, limit: int = 10) -> list:
        """Get audit history for a client."""
        return self._query(
            """SELECT * FROM audit_logs 
               WHERE client_id = ? 
               ORDER BY executed_at DESC 
               LIMIT ?""",
            (client_id, limit)
        )
    
    # =======================
    # ACTION ITEMS
    # =======================
    
    def add_action_item(self, client_id: int, title: str, description: str = None,
                        priority: str = 'medium', category: str = None,
                        effort: float = None, impact: str = None,
                        week: int = None) -> int:
        """Add action item to roadmap."""
        return self._query(
            """INSERT INTO action_items 
               (client_id, task_title, description, priority, category, 
                effort_hours, estimated_impact, roadmap_week)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (client_id, title, description, priority, category, effort, impact, week),
            fetch='last_id'
        )
    
    def get_action_items(self, client_id: int = None, status: str = 'pending') -> list:
        """Get action items, optionally filtered."""
        if client_id:
            return self._query(
                """SELECT * FROM action_items 
                   WHERE client_id = ? AND status = ?
                   ORDER BY roadmap_week ASC, priority DESC""",
                (client_id, status)
            )
        return self._query(
            "SELECT * FROM action_items WHERE status = ? ORDER BY priority DESC",
            (status,)
        )
    
    def complete_action_item(self, action_id: int):
        """Mark action item as completed."""
        self._query(
            "UPDATE action_items SET status = 'completed', completed_date = ? WHERE action_id = ?",
            (datetime.now().isoformat(), action_id)
        )
    
    # =======================
    # REPORTING
    # =======================
    
    def generate_monthly_summary(self, client_id: int, month: str) -> dict:
        """Generate monthly summary for a client."""
        client = self.get_client(client_id=client_id)
        kpis = self._query(
            "SELECT * FROM monthly_kpis WHERE client_id = ? AND report_month = ?",
            (client_id, month),
            fetch='one'
        )
        position_changes = self.calculate_position_changes(client_id)
        pending_actions = self.get_action_items(client_id, 'pending')
        audits = self.get_audit_history(client_id, 3)
        
        return {
            'client': client,
            'month': month,
            'kpis': kpis,
            'position_changes': position_changes,
            'pending_actions': len(pending_actions),
            'recent_audits': audits
        }
    
    def get_dashboard_data(self, client_id: int = None) -> dict:
        """Get data needed for dashboard rendering."""
        if client_id:
            clients = [self.get_client(client_id=client_id)]
        else:
            clients = self.list_clients()
        
        dashboard = []
        for client in clients:
            if not client:
                continue
            
            kpis = self.get_kpi_trend(client['client_id'], 3)
            keywords = self.get_keyword_rankings(client['client_id'], 10)
            actions = self.get_action_items(client['client_id'], 'pending')
            
            dashboard.append({
                'client': client,
                'kpi_trend': kpis,
                'top_keywords': keywords,
                'pending_actions': len(actions),
                'action_summary': actions[:3]  # First 3
            })
        
        return {
            'clients': dashboard,
            'total_clients': len(clients),
            'generated_at': datetime.now().isoformat()
        }


# Convenience function
def get_db() -> SEODatabase:
    """Get database instance."""
    return SEODatabase()


if __name__ == "__main__":
    # Test database
    db = get_db()
    
    # Add test client
    client_id = db.add_client(
        domain="uncorkedcanvas.com",
        business_name="Uncorked Canvas",
        business_model="hybrid"
    )
    print(f"Added client with ID: {client_id}")
    
    # Record initial KPIs
    db.record_monthly_kpis(
        client_id=client_id,
        month="2026-03",
        traffic=4200,
        avg_rank=22.4,
        keywords=156,
        backlinks=340,
        conversions=48
    )
    
    # Track some keywords
    for kw, rank in [("paint and sip gig harbor", 5), 
                    ("paint and sip seattle", 12),
                    ("at home paint kit", 8)]:
        db.track_keyword(client_id, kw, volume=1000, difficulty=35, 
                        intent="local_service_search", current_rank=rank)
    
    # Add action items
    db.add_action_item(client_id, "Claim Google Business Profile", 
                      "Verify all locations have claimed GBP",
                      priority="critical", category="local", effort=1, week=1)
    db.add_action_item(client_id, "Add Brand schema to products",
                      "Add missing schema markup",
                      priority="high", category="ecommerce", effort=2, week=2)
    
    # Get dashboard
    data = db.get_dashboard_data(client_id)
    print(f"\nDashboard: {json.dumps(data, indent=2, default=str)}")