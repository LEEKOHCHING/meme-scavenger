-- ============================================================
-- Migration 003: token_metrics
-- Daily trading snapshots from DexScreener for all graduated tokens.
-- One row per token per snapshot_date (UNIQUE constraint).
-- ============================================================

IF NOT EXISTS (
    SELECT 1 FROM sys.tables WHERE name = 'token_metrics'
)
BEGIN
    CREATE TABLE token_metrics (
        id               BIGINT         IDENTITY(1,1) PRIMARY KEY,
        address          VARCHAR(100)   NOT NULL,           -- token contract address
        snapshot_date    DATE           NOT NULL,           -- date of this snapshot
        checked_at       DATETIME2      NOT NULL DEFAULT GETDATE(),

        -- Best pair selected by highest liquidity_usd
        pair_address     VARCHAR(100)   NULL,
        dex_id           VARCHAR(50)    NULL,
        pair_count       INT            NOT NULL DEFAULT 0, -- total pairs found on DexScreener

        -- Price
        price_usd        DECIMAL(30,10) NULL,
        price_change_m5  FLOAT          NULL,
        price_change_h1  FLOAT          NULL,
        price_change_h6  FLOAT          NULL,
        price_change_h24 FLOAT          NULL,

        -- Volume (USD)
        volume_m5        FLOAT          NULL,
        volume_h1        FLOAT          NULL,
        volume_h6        FLOAT          NULL,
        volume_h24       FLOAT          NULL,

        -- Liquidity & Market Cap
        liquidity_usd    FLOAT          NULL,
        market_cap       FLOAT          NULL,
        fdv              FLOAT          NULL,

        -- Transactions
        txns_h1_buys     INT            NULL,
        txns_h1_sells    INT            NULL,
        txns_h24_buys    INT            NULL,
        txns_h24_sells   INT            NULL,

        -- Raw best-pair JSON
        raw_json         NVARCHAR(MAX)  NULL,

        CONSTRAINT UQ_token_metrics_addr_date UNIQUE (address, snapshot_date)
    );

    CREATE INDEX IX_token_metrics_address ON token_metrics (address);
    CREATE INDEX IX_token_metrics_date    ON token_metrics (snapshot_date DESC);
    CREATE INDEX IX_token_metrics_vol24   ON token_metrics (volume_h24 DESC);

    PRINT 'Created table token_metrics';
END
ELSE
    PRINT 'Table token_metrics already exists — skipped.';
