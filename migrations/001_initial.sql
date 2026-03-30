-- =============================================================================
-- Fintelligence — PostgreSQL Multi-Tenant Schema
-- Migration: 001_initial
-- Run automatically by postgres on first container boot (initdb.d)
-- =============================================================================

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()

-- =============================================================================
-- SHARED: Users + Auth (owned by Volguard, read by all services via shared JWT)
-- =============================================================================

CREATE TABLE IF NOT EXISTS users (
    id                  SERIAL PRIMARY KEY,
    email               VARCHAR(255) NOT NULL UNIQUE,
    hashed_password     VARCHAR(255) NOT NULL,
    -- NOTE (Option B): upstox_token is NOT stored here.
    -- The broker token lives only on the user's device (sessionStorage).
    -- The server never receives or persists it.
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
    is_admin            BOOLEAN     NOT NULL DEFAULT FALSE,
    subscription_tier   VARCHAR(20) NOT NULL DEFAULT 'free',  -- free | pro | team
    subscription_expires_at TIMESTAMPTZ NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at       TIMESTAMPTZ NULL,
    last_invalidated_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS admin_audit_log (
    id             SERIAL PRIMARY KEY,
    admin_id       INTEGER     NOT NULL,
    action         VARCHAR(50) NOT NULL,
    target_user_id INTEGER     NULL,
    detail         VARCHAR(500) NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_admin ON admin_audit_log(admin_id);

-- =============================================================================
-- VOLGUARD: Options trading journal + config
-- =============================================================================

CREATE TABLE IF NOT EXISTS dynamic_config (
    id         SERIAL PRIMARY KEY,
    key        VARCHAR(100) NOT NULL,
    value      TEXT         NOT NULL,
    user_id    INTEGER      NULL REFERENCES users(id) ON DELETE CASCADE,
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (key, user_id)                  -- NULL user_id = global default
);
CREATE INDEX IF NOT EXISTS idx_dyncfg_user ON dynamic_config(user_id);

CREATE TABLE IF NOT EXISTS trades (
    id                       SERIAL PRIMARY KEY,
    user_id                  INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_id              VARCHAR(64) NOT NULL,
    strategy_type            VARCHAR(50),
    expiry_type              VARCHAR(20),
    expiry_date              TIMESTAMPTZ,
    entry_time               TIMESTAMPTZ,
    exit_time                TIMESTAMPTZ NULL,
    legs_data                JSONB,
    order_ids                JSONB,
    filled_quantities        JSONB  NULL,
    fill_prices              JSONB  NULL,
    gtt_order_ids            JSONB  NULL,
    entry_greeks_snapshot    JSONB  NULL,
    max_profit               FLOAT,
    max_loss                 FLOAT,
    allocated_capital        FLOAT,
    required_margin          FLOAT  DEFAULT 0,
    entry_premium            FLOAT,
    exit_premium             FLOAT  NULL,
    realized_pnl             FLOAT  NULL,
    pnl_approximate          BOOLEAN DEFAULT FALSE,
    theta_pnl                FLOAT  NULL,
    vega_pnl                 FLOAT  NULL,
    gamma_pnl                FLOAT  NULL,
    status                   VARCHAR(20),
    exit_reason              VARCHAR(100) NULL,
    is_mock                  BOOLEAN DEFAULT FALSE,
    associated_event_date    TIMESTAMPTZ NULL,
    associated_event_name    VARCHAR(100) NULL,
    regime_score_at_entry    FLOAT  NULL,
    vix_at_entry             FLOAT  NULL,
    ivp_at_entry             FLOAT  NULL,
    vol_regime_at_entry      VARCHAR(20) NULL,
    morning_tone_at_entry    VARCHAR(20) NULL,
    pretrade_verdict_at_entry VARCHAR(30) NULL,
    vov_zscore_at_entry      FLOAT  NULL,
    weighted_vrp_at_entry    FLOAT  NULL,
    score_drivers_at_entry   JSONB  NULL,
    pretrade_rationale       VARCHAR(500) NULL,
    trade_outcome_class      VARCHAR(20) NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, strategy_id)
);
CREATE INDEX IF NOT EXISTS idx_trades_user    ON trades(user_id);
CREATE INDEX IF NOT EXISTS idx_trades_status  ON trades(user_id, status);
CREATE INDEX IF NOT EXISTS idx_trades_entry   ON trades(user_id, entry_time DESC);

CREATE TABLE IF NOT EXISTS daily_stats (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date           DATE        NOT NULL,
    total_pnl      FLOAT DEFAULT 0,
    realized_pnl   FLOAT DEFAULT 0,
    unrealized_pnl FLOAT DEFAULT 0,
    trades_count   INTEGER DEFAULT 0,
    wins           INTEGER DEFAULT 0,
    losses         INTEGER DEFAULT 0,
    largest_win    FLOAT DEFAULT 0,
    largest_loss   FLOAT DEFAULT 0,
    max_drawdown   FLOAT DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, date)
);
CREATE INDEX IF NOT EXISTS idx_daily_user ON daily_stats(user_id, date DESC);

CREATE TABLE IF NOT EXISTS veto_log (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    regime_score FLOAT,
    vix          FLOAT,
    reason       VARCHAR(500),
    overridden   BOOLEAN DEFAULT FALSE,
    override_reason VARCHAR(500) NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_veto_user ON veto_log(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS intelligence_briefs (
    id           SERIAL PRIMARY KEY,
    -- Briefs are global (same macro context for all users) — no user_id
    brief_date   DATE        NOT NULL UNIQUE,
    tone         VARCHAR(20),
    summary      TEXT,
    full_json    JSONB,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- MF: Mutual Fund analysis cache (shared across users — same fund data)
-- =============================================================================

CREATE TABLE IF NOT EXISTS mf_analysis_cache (
    id          SERIAL PRIMARY KEY,
    cache_key   VARCHAR(64) NOT NULL UNIQUE,
    scheme_code VARCHAR(20),
    fund_type   VARCHAR(20),
    result_json TEXT,
    status      VARCHAR(20) DEFAULT 'pending',
    error_msg   VARCHAR(500) NULL,
    with_regime BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mf_cache_key     ON mf_analysis_cache(cache_key);
CREATE INDEX IF NOT EXISTS idx_mf_cache_expires ON mf_analysis_cache(expires_at);

CREATE TABLE IF NOT EXISTS mf_search_cache (
    id          SERIAL PRIMARY KEY,
    query_hash  VARCHAR(64) NOT NULL UNIQUE,
    query       VARCHAR(200),
    result_json TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS mf_analysis_history (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scheme_code VARCHAR(20),
    scheme_name VARCHAR(200),
    fund_type   VARCHAR(20),
    conviction  VARCHAR(50) NULL,
    analysed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_mf_history_user ON mf_analysis_history(user_id, analysed_at DESC);

-- =============================================================================
-- EQUITY: Stock analysis cache (shared across users)
-- =============================================================================

CREATE TABLE IF NOT EXISTS equity_analysis_cache (
    id           SERIAL PRIMARY KEY,
    cache_key    VARCHAR(64) NOT NULL UNIQUE,
    bse_code     VARCHAR(20),
    nse_symbol   VARCHAR(20),
    company_name VARCHAR(200),
    sector       VARCHAR(50),
    result_json  TEXT,
    status       VARCHAR(20) DEFAULT 'pending',
    error_msg    VARCHAR(500) NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at   TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_equity_cache_expires ON equity_analysis_cache(expires_at);

CREATE TABLE IF NOT EXISTS equity_search_cache (
    id          SERIAL PRIMARY KEY,
    query_hash  VARCHAR(64) NOT NULL UNIQUE,
    result_json TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS equity_analysis_history (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bse_code     VARCHAR(20),
    company_name VARCHAR(200),
    sector       VARCHAR(50),
    conviction   VARCHAR(50) NULL,
    analysed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_equity_history_user ON equity_analysis_history(user_id, analysed_at DESC);

-- =============================================================================
-- TAX: Per-user portfolio data (inherently private)
-- =============================================================================

CREATE TABLE IF NOT EXISTS tax_portfolios (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    portfolio_json TEXT    NOT NULL,
    zerodha_file   VARCHAR(255) NULL,
    cams_file      VARCHAR(255) NULL,
    uploaded_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- SUBSCRIPTIONS: Razorpay payment tracking
-- =============================================================================

CREATE TABLE IF NOT EXISTS subscription_payments (
    id                 SERIAL PRIMARY KEY,
    user_id            INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    razorpay_order_id  VARCHAR(100) NOT NULL UNIQUE,
    razorpay_payment_id VARCHAR(100) NULL,
    amount_paise       INTEGER      NOT NULL,   -- in paise (₹499 = 49900)
    currency           VARCHAR(10)  NOT NULL DEFAULT 'INR',
    tier               VARCHAR(20)  NOT NULL,   -- pro | team
    months             INTEGER      NOT NULL DEFAULT 1,
    status             VARCHAR(20)  NOT NULL DEFAULT 'created',  -- created | paid | failed
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    paid_at            TIMESTAMPTZ  NULL
);
CREATE INDEX IF NOT EXISTS idx_payments_user ON subscription_payments(user_id, created_at DESC);

-- =============================================================================
-- Trigger: auto-update updated_at on trades
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trades_updated_at ON trades;
CREATE TRIGGER trades_updated_at
    BEFORE UPDATE ON trades
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Done
