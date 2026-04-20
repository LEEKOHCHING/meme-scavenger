-- 006_purchase_tokens.sql
-- Stores the actual demo swap results (one row per token per purchase).
-- Replaces the single random item_drop for demo-mode purchases.

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'purchase_tokens'
)
BEGIN
    CREATE TABLE purchase_tokens (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        purchase_id     INT           NOT NULL REFERENCES purchases(id),
        token_address   NVARCHAR(42),
        token_name      NVARCHAR(200),
        token_symbol    NVARCHAR(50),
        img_url         NVARCHAR(500),
        amount_received NVARCHAR(50),   -- formatted whole-number string, e.g. "1,234,567"
        swap_tx_hash    NVARCHAR(66),
        success         BIT           NOT NULL DEFAULT 1,
        created_at      DATETIME2     NOT NULL DEFAULT GETDATE()
    );

    CREATE INDEX IX_purchase_tokens_purchase_id
        ON purchase_tokens (purchase_id);
END
