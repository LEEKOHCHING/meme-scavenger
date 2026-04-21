-- Add X activity score and report directly to graduated_tokens
-- x_score:     0-100  (0 = dead/no posts, 100 = highly active)
-- x_report:    Grok-generated analysis text
-- x_scored_at: timestamp of last scoring run

ALTER TABLE graduated_tokens
ADD x_score     INT           NULL,
    x_report    NVARCHAR(MAX) NULL,
    x_scored_at DATETIME2     NULL;
