-- Add demo flag to graduated_tokens
-- demo = 1 → token is included in the Demo Mode swap distribution
ALTER TABLE graduated_tokens ADD demo BIT NOT NULL DEFAULT 0;
