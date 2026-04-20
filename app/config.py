from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mssql_server: str
    mssql_database: str
    mssql_user: str
    mssql_password: str
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "development"
    bsc_rpc_url: str = "https://bsc-dataseed.binance.org/"
    bsc_contract_address: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    humanize_model: str = "claude-sonnet-4-5"
    sophia_interval: int = 30
    # Twitter / X API
    twitter_bearer_token: str = ""
    twitter_client_id: str = ""
    twitter_client_secret: str = ""
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_token_secret: str = ""
    # BSC on-chain scanner
    four_meme_v1_contract: str = ""          # not used (V1 address was incorrect)
    four_meme_v2_contract: str = "0x5c952063c7fc8610FFDB798152D69F0B9550762b"
    four_meme_start_block: int = 37_500_000  # Four.meme first active ~block 38M (April 2024)
    chain_scan_chunk:      int = 2000        # blocks per eth_getLogs call (Alchemy-safe)
    # Demo mode hot wallet (server-side swap executor)
    hot_wallet_address:     str = ""
    hot_wallet_private_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "env_ignore_empty": True}


settings = Settings()
