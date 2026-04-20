-- Migration 004: Persistent cursor for BSC on-chain scanner
-- Run once against memeDB

CREATE TABLE scan_state (
    scan_key  NVARCHAR(100) NOT NULL,
    value     NVARCHAR(500) NOT NULL,
    CONSTRAINT PK_scan_state PRIMARY KEY (scan_key)
);

-- Seed with Four.meme approximate launch block.
-- The scanner will advance these forward automatically on each run.
INSERT INTO scan_state (scan_key, value) VALUES
    ('four_meme_v1_last_block', '44000000'),
    ('four_meme_v2_last_block', '44000000');
