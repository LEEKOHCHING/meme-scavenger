from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class PurchaseRequest(BaseModel):
    wallet_address: str
    tier: int          # 0=Basic, 1=Elite, 2=Mythic
    price_u: int
    tx_hash: str       # BSC transaction hash — verified before recording


class PurchaseResponse(BaseModel):
    id: int
    wallet_address: str
    tier: int
    price_u: int
    tx_hash: str
    created_at: datetime


class LiveMessage(BaseModel):
    id: int
    user_name: str
    color: str
    message: str
    created_at: datetime


class ItemDrop(BaseModel):
    id: int
    purchase_id: int
    token_name: str
    token_symbol: str
    rarity: str
    image_url: Optional[str] = None
