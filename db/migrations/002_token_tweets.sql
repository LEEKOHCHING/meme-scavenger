-- ============================================================
-- Migration 002: token_tweets
-- Stores live tweets from tracked token Twitter accounts.
-- Run once against memeDB.
-- ============================================================

IF NOT EXISTS (
    SELECT 1 FROM sys.tables WHERE name = 'token_tweets'
)
BEGIN
    CREATE TABLE token_tweets (
        id               BIGINT        IDENTITY(1,1) PRIMARY KEY,
        tweet_id         VARCHAR(30)   NOT NULL,           -- Twitter numeric ID
        token_address    VARCHAR(100)  NULL,               -- matched graduated token
        twitter_handle   VARCHAR(100)  NULL,               -- @handle that tweeted
        author_id        VARCHAR(30)   NULL,               -- Twitter user ID
        text             NVARCHAR(1000) NULL,              -- tweet full text
        lang             VARCHAR(10)   NULL,               -- detected language
        tweet_created_at DATETIME2     NULL,               -- tweet's own timestamp
        retweet_count    INT           NOT NULL DEFAULT 0,
        like_count       INT           NOT NULL DEFAULT 0,
        reply_count      INT           NOT NULL DEFAULT 0,
        quote_count      INT           NOT NULL DEFAULT 0,
        is_retweet       BIT           NOT NULL DEFAULT 0,
        is_reply         BIT           NOT NULL DEFAULT 0,
        stream_rule_tag  VARCHAR(200)  NULL,               -- which stream rule matched
        raw_json         NVARCHAR(MAX) NULL,
        scraped_at       DATETIME2     NOT NULL DEFAULT GETDATE(),

        CONSTRAINT UQ_token_tweets_tweet_id UNIQUE (tweet_id)
    );

    CREATE INDEX IX_token_tweets_address  ON token_tweets (token_address);
    CREATE INDEX IX_token_tweets_handle   ON token_tweets (twitter_handle);
    CREATE INDEX IX_token_tweets_created  ON token_tweets (tweet_created_at DESC);

    PRINT 'Created table token_tweets';
END
ELSE
    PRINT 'Table token_tweets already exists — skipped.';
