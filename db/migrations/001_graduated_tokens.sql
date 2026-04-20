-- Migration 001: Four.meme graduated token archive
-- Run once against memeDB

CREATE TABLE graduated_tokens (
    id              INT IDENTITY(1,1) PRIMARY KEY,

    -- Identity
    address         NVARCHAR(42)    NOT NULL,   -- token contract address (unique key)
    name            NVARCHAR(255)   NULL,
    symbol          NVARCHAR(50)    NULL,
    description     NVARCHAR(MAX)   NULL,
    label           NVARCHAR(100)   NULL,       -- Meme | AI | Defi | Games | Infra | Social | ...

    -- Images
    img_url         NVARCHAR(1000)  NULL,       -- original CDN URL from Four.meme
    img_local       NVARCHAR(500)   NULL,       -- local path served via /images/tokens/<file>

    -- Tokenomics
    total_supply    NVARCHAR(100)   NULL,
    raised_amount   NVARCHAR(100)   NULL,       -- BNB raised during bonding curve
    sale_rate       NVARCHAR(50)    NULL,
    reserve_rate    NVARCHAR(50)    NULL,
    launch_time     BIGINT          NULL,       -- Unix timestamp (ms)

    -- Market data (snapshot at scrape time)
    last_price      NVARCHAR(100)   NULL,
    market_cap      NVARCHAR(100)   NULL,
    volume_24h      NVARCHAR(100)   NULL,
    holder_count    INT             NULL,
    progress        FLOAT           NULL,       -- bonding curve % at graduation (should be ~100)

    -- Social / links
    web_url         NVARCHAR(500)   NULL,
    twitter_url     NVARCHAR(500)   NULL,
    telegram_url    NVARCHAR(500)   NULL,

    -- Platform metadata
    dex_type        NVARCHAR(50)    NULL,       -- PANCAKE_SWAP
    version         NVARCHAR(20)    NULL,       -- V9 | V10
    list_type       NVARCHAR(50)    NULL,       -- NOR | BIN | USD1 | ADV ...
    is_ai_created   BIT             NULL,       -- created by AI agent
    fee_plan        BIT             NULL,       -- tax token flag
    creator_address NVARCHAR(42)    NULL,

    -- Raw data
    raw_json        NVARCHAR(MAX)   NULL,       -- full API payload, nothing lost

    -- Housekeeping
    scraped_at      DATETIME2       NOT NULL DEFAULT GETDATE(),
    updated_at      DATETIME2       NOT NULL DEFAULT GETDATE(),

    CONSTRAINT uq_graduated_address UNIQUE (address)
);

-- Index for fast symbol/label lookups
CREATE INDEX ix_graduated_symbol ON graduated_tokens (symbol);
CREATE INDEX ix_graduated_label  ON graduated_tokens (label);
CREATE INDEX ix_graduated_launch ON graduated_tokens (launch_time DESC);
