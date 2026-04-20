-- Run this once against memeDB to create all tables

CREATE TABLE purchases (
    id             INT IDENTITY(1,1) PRIMARY KEY,
    wallet_address NVARCHAR(100) NOT NULL,
    tier           TINYINT       NOT NULL,  -- 0=Basic 1=Elite 2=Mythic
    price_u        INT           NOT NULL,
    tx_hash        NVARCHAR(66)  NOT NULL UNIQUE,  -- BSC tx hash, prevents double-redeem
    created_at     DATETIME2     NOT NULL DEFAULT GETDATE()
);

CREATE TABLE item_drops (
    id           INT IDENTITY(1,1) PRIMARY KEY,
    purchase_id  INT           NOT NULL REFERENCES purchases(id),
    token_name   NVARCHAR(100) NOT NULL,
    token_symbol NVARCHAR(20)  NOT NULL,
    rarity       NVARCHAR(20)  NOT NULL,  -- common / rare / mythic
    image_url    NVARCHAR(500) NULL,
    created_at   DATETIME2     NOT NULL DEFAULT GETDATE()
);

CREATE TABLE live_messages (
    id         INT IDENTITY(1,1) PRIMARY KEY,
    user_name  NVARCHAR(100) NOT NULL,
    color      NVARCHAR(20)  NOT NULL DEFAULT '#39FF14',
    message    NVARCHAR(500) NOT NULL,
    created_at DATETIME2     NOT NULL DEFAULT GETDATE()
);

-- Seed initial live messages
INSERT INTO live_messages (user_name, color, message) VALUES
('Sophia', '#39FF14', 'Scanning 847 tokens on-chain... found a hidden gem 💎'),
('Sophia', '#39FF14', 'This token''s volume just spiked 300% with zero news — digging deeper 🔍'),
('Sophia', '#39FF14', '3AM and I''m still here. Ruins don''t sleep, neither do I 🌙'),
('Sophia', '#39FF14', 'Whale wallet just accumulated quietly. Something''s brewing 🐋'),
('Sophia', '#39FF14', 'Cross-referencing social signals with on-chain data... 🤖');
