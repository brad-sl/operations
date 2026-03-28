-- SEO Agent Tracking Database
-- Multi-client, multi-metric analytics with historical trend tracking

CREATE TABLE IF NOT EXISTS clients (
    client_id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT UNIQUE NOT NULL,
    business_name TEXT NOT NULL,
    business_model TEXT NOT NULL,  -- 'saas', 'ecommerce', 'local', 'hybrid', 'publisher'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_audit DATETIME,
    status TEXT DEFAULT 'active'  -- 'active', 'paused', 'inactive'
);

-- Monthly KPI Snapshots (for dashboards and trend analysis)
CREATE TABLE IF NOT EXISTS monthly_kpis (
    kpi_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    report_month TEXT NOT NULL,  -- 'YYYY-MM'
    organic_traffic INTEGER,
    avg_ranking REAL,
    total_keywords_ranking INTEGER,
    indexed_pages INTEGER,
    backlinks INTEGER,
    referring_domains INTEGER,
    domain_authority REAL,
    organic_conversions INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(client_id) REFERENCES clients(client_id),
    UNIQUE(client_id, report_month)
);

-- Keyword Rankings (track per keyword history)
CREATE TABLE IF NOT EXISTS keyword_rankings (
    ranking_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    keyword TEXT NOT NULL,
    search_volume INTEGER,
    difficulty REAL,
    intent TEXT,  -- 'informational', 'commercial', 'transactional', 'navigational'
    current_rank INTEGER,
    previous_rank INTEGER,
    change_direction TEXT,  -- 'up', 'down', 'stable'
    position_change INTEGER,
    tracked_since DATETIME,
    last_checked DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(client_id) REFERENCES clients(client_id),
    UNIQUE(client_id, keyword)
);

-- Keyword History (full audit trail for trend analysis)
CREATE TABLE IF NOT EXISTS keyword_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ranking_id INTEGER NOT NULL,
    rank_position INTEGER NOT NULL,
    checked_date DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(ranking_id) REFERENCES keyword_rankings(ranking_id)
);

-- Audit Execution Log
CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    prompt_id TEXT,  -- 'prompt-0', 'prompt-7', etc
    prompt_name TEXT,
    status TEXT,  -- 'completed', 'in_progress', 'failed'
    findings_count INTEGER,
    recommendations_count INTEGER,
    executed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    execution_time_seconds REAL,
    report_file_path TEXT,
    FOREIGN KEY(client_id) REFERENCES clients(client_id)
);

-- Local SEO Metrics (for local service businesses)
CREATE TABLE IF NOT EXISTS local_seo_metrics (
    local_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    location_name TEXT,  -- 'Gig Harbor', 'Seattle', etc
    gbp_views INTEGER,
    gbp_direction_requests INTEGER,
    gbp_phone_calls INTEGER,
    citation_count INTEGER,
    nap_consistency REAL,  -- percentage
    local_rank_position REAL,  -- for geo-modified keywords
    report_month TEXT,  -- 'YYYY-MM'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(client_id) REFERENCES clients(client_id),
    UNIQUE(client_id, location_name, report_month)
);

-- E-commerce Metrics
CREATE TABLE IF NOT EXISTS ecommerce_metrics (
    ecom_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    product_category TEXT,  -- 'art kits', 'blankets', etc
    product_pages_count INTEGER,
    product_avg_rank REAL,
    product_traffic INTEGER,
    product_conversions INTEGER,
    conversion_rate REAL,
    avg_order_value REAL,
    schema_markup_score REAL,  -- percentage
    report_month TEXT,  -- 'YYYY-MM'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(client_id) REFERENCES clients(client_id),
    UNIQUE(client_id, product_category, report_month)
);

-- Content Performance
CREATE TABLE IF NOT EXISTS content_performance (
    content_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    page_url TEXT,
    page_title TEXT,
    content_type TEXT,  -- 'blog', 'product', 'location', 'guide', 'comparison'
    organic_traffic INTEGER,
    keywords_ranking INTEGER,
    primary_keyword TEXT,
    primary_keyword_rank INTEGER,
    backlinks_to_page INTEGER,
    internal_links_to_page INTEGER,
    last_updated DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(client_id) REFERENCES clients(client_id),
    UNIQUE(client_id, page_url)
);

-- Backlink Intelligence
CREATE TABLE IF NOT EXISTS backlinks (
    backlink_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    referring_domain TEXT,
    referring_url TEXT,
    link_anchor_text TEXT,
    domain_authority REAL,
    link_date_found DATETIME,
    status TEXT,  -- 'active', 'lost', 'nofollow'
    source_type TEXT,  -- 'directory', 'guest_post', 'press', 'partnership', 'natural'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(client_id) REFERENCES clients(client_id),
    UNIQUE(client_id, referring_url)
);

-- Roadmap & Action Items
CREATE TABLE IF NOT EXISTS action_items (
    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    task_title TEXT NOT NULL,
    description TEXT,
    priority TEXT,  -- 'critical', 'high', 'medium', 'low'
    category TEXT,  -- 'technical', 'content', 'local', 'links', 'ecommerce'
    effort_hours REAL,
    estimated_impact TEXT,
    status TEXT DEFAULT 'pending',  -- 'pending', 'in_progress', 'completed', 'blocked'
    due_date DATETIME,
    completed_date DATETIME,
    roadmap_week INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(client_id) REFERENCES clients(client_id)
);

-- Competitive Intelligence Snapshots
CREATE TABLE IF NOT EXISTS competitor_intel (
    competitor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    competitor_domain TEXT,
    competitor_name TEXT,
    ranking_position_avg REAL,
    backlink_count INTEGER,
    estimated_traffic REAL,
    content_pages_count INTEGER,
    keywords_advantage TEXT,  -- 'we lead', 'competitor leads', 'tied'
    last_analyzed DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(client_id) REFERENCES clients(client_id),
    UNIQUE(client_id, competitor_domain)
);

-- Monthly Reports (metadata)
CREATE TABLE IF NOT EXISTS reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    report_month TEXT NOT NULL,  -- 'YYYY-MM'
    report_type TEXT,  -- 'monthly', 'quarterly', 'audit', 'competitive'
    report_file_path TEXT,
    traffic_change_pct REAL,
    ranking_change_avg REAL,
    keywords_gained INTEGER,
    keywords_lost INTEGER,
    recommendations_count INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(client_id, report_month, report_type)
);

-- Create Indexes for Performance
CREATE INDEX idx_clients_domain ON clients(domain);
CREATE INDEX idx_monthly_kpis_client_month ON monthly_kpis(client_id, report_month);
CREATE INDEX idx_keyword_rankings_client ON keyword_rankings(client_id);
CREATE INDEX idx_keyword_history_ranking ON keyword_history(ranking_id);
CREATE INDEX idx_audit_logs_client ON audit_logs(client_id);
CREATE INDEX idx_action_items_client_status ON action_items(client_id, status);
