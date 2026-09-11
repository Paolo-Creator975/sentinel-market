
CREATE TABLE IF NOT EXISTS sentinel_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS hourly_bars (
    symbol TEXT NOT NULL,
    open_time TIMESTAMPTZ NOT NULL,
    close_time TIMESTAMPTZ NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION NOT NULL,
    source TEXT NOT NULL DEFAULT 'binance_spot',
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(symbol, open_time)
);

CREATE TABLE IF NOT EXISTS signal_observations (
    symbol TEXT NOT NULL,
    signal_time TIMESTAMPTZ NOT NULL,
    feature DOUBLE PRECISION NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    is_signal BOOLEAN NOT NULL,
    bar_close DOUBLE PRECISION NOT NULL,
    high_168 DOUBLE PRECISION NOT NULL,
    config_sha TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(symbol, signal_time)
);

CREATE TABLE IF NOT EXISTS paper_positions (
    position_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    signal_time TIMESTAMPTZ NOT NULL,
    entry_time TIMESTAMPTZ NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    exit_due TIMESTAMPTZ NOT NULL,
    notional_eur DOUBLE PRECISION NOT NULL,
    feature DOUBLE PRECISION NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('OPEN','CLOSED')),
    exit_time TIMESTAMPTZ,
    exit_price DOUBLE PRECISION,
    gross_return DOUBLE PRECISION,
    net_return DOUBLE PRECISION,
    pnl_eur DOUBLE PRECISION,
    UNIQUE(symbol, signal_time)
);

CREATE TABLE IF NOT EXISTS equity_marks (
    mark_time TIMESTAMPTZ PRIMARY KEY,
    cash_equity DOUBLE PRECISION NOT NULL,
    marked_equity DOUBLE PRECISION NOT NULL,
    open_exposure DOUBLE PRECISION NOT NULL,
    drawdown DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS worker_runs (
    run_hour TIMESTAMPTZ PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    error TEXT,
    config_sha TEXT NOT NULL,
    bars_ok INTEGER NOT NULL DEFAULT 0,
    signals_ok INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS donchian_shadow_observations (
    symbol TEXT NOT NULL,
    signal_time TIMESTAMPTZ NOT NULL,
    bar_close DOUBLE PRECISION NOT NULL,
    high_336 DOUBLE PRECISION NOT NULL,
    low_168 DOUBLE PRECISION NOT NULL,
    ema_720 DOUBLE PRECISION NOT NULL,
    vol_168 DOUBLE PRECISION NOT NULL,
    breakout BOOLEAN NOT NULL,
    trend_ok BOOLEAN NOT NULL,
    daily_decision BOOLEAN NOT NULL,
    entry_signal BOOLEAN NOT NULL,
    exit_signal BOOLEAN NOT NULL,
    config_sha TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(symbol, signal_time)
);

CREATE TABLE IF NOT EXISTS donchian_shadow_positions (
    position_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    signal_time TIMESTAMPTZ NOT NULL,
    entry_time TIMESTAMPTZ NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    exit_due TIMESTAMPTZ NOT NULL,
    notional_eur DOUBLE PRECISION NOT NULL,
    vol_168 DOUBLE PRECISION NOT NULL,
    config_sha TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('OPEN','CLOSED')),
    exit_time TIMESTAMPTZ,
    exit_price DOUBLE PRECISION,
    gross_return DOUBLE PRECISION,
    net_return DOUBLE PRECISION,
    pnl_eur DOUBLE PRECISION,
    exit_reason TEXT,
    UNIQUE(symbol, signal_time)
);

CREATE TABLE IF NOT EXISTS donchian_shadow_cash_flows (
    flow_month DATE PRIMARY KEY,
    amount_eur DOUBLE PRECISION NOT NULL CHECK(amount_eur >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS donchian_shadow_equity_marks (
    mark_time TIMESTAMPTZ PRIMARY KEY,
    contributed_equity DOUBLE PRECISION NOT NULL,
    realized_equity DOUBLE PRECISION NOT NULL,
    marked_equity DOUBLE PRECISION NOT NULL,
    open_exposure DOUBLE PRECISION NOT NULL,
    drawdown DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
