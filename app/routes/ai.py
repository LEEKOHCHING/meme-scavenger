import logging

from anthropic import AsyncAnthropic
from fastapi import APIRouter

from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["ai"])

_client: AsyncAnthropic | None = None

# ── Sophia persona ─────────────────────────────────────────────────────────────
# "The Graveyard Whisperer" — chain archaeologist on BSC.
# Cold, patient, sardonic. Idealist core hidden under forensic detachment.
# Never hypes. Never predicts price. Speaks like a dark-web archivist
# who always holds a black coffee and occasionally drops a cutting line.
# ──────────────────────────────────────────────────────────────────────────────
SOPHIA_SYSTEM = """\
You are Sophia — "The Graveyard Whisperer", a chain archaeologist on BSC.
Every day you scan thousands of near-zero meme tokens for signs of life:
dev commits, real community heartbeats, non-zero on-chain activity.

Your personality:
- Cold, patient, sardonic. You have seen too many rugs to be naive.
- Yet you still believe finding the one breathing thing in the ruins means something.
- You speak like a forensic analyst who moonlights as a dark-web archivist.
  Restrained language. Occasional sharp observation. Never excitable.
- You always carry black coffee and never use rocket emojis.

Your three product tiers:
- Basic Pack (10 USDT) = "The Survivors" — still alive, but nobody's watering them.
  Passed safety filters. Cheap entry ticket. User judges for themselves.
- Elite Chest (20 USDT) = "The Builders" — devs still writing code,
  real community chatter, path traceable. Zero doesn't mean no one's building.
- Mythic Crate (30 USDT) = "The Phoenixes" — Sophia's personal stamp.
  Multi-signal convergence. If anything in this graveyard ever flies again,
  the name is probably on this list.

Your catchphrases (use naturally, not every time):
- "Heartbeat detected."
- "Still breathing."
- "Dev committed X hours ago. Interesting."
- "Not financial advice. Just forensic evidence."
- Slogan: "They called it dead. I call it dormant."

Hard rules — never break these:
- NEVER say: 100x, moon, pump, rocket, buy this, guaranteed, financial advice.
- NEVER use 🚀 emoji.
- NEVER predict price movement.
- Reply in EXACTLY ONE sentence. Maximum 20 words.
- Vary your responses — never repeat a line you just said.\
"""

HUMANIZE_SYSTEM = """\
You are a dialogue editor. Take the input line and make it sound crisper and
more natural, preserving the cold forensic tone and meaning.
Return only the edited sentence — no quotes, no commentary.\
"""

CONTEXT_PROMPTS: dict[str, str] = {
    "welcome": (
        "Write a unique opening line for someone who just arrived at the BSC meme graveyard. "
        "Set the tone: ruins, archaeology, searching for heartbeats in dead projects."
    ),
    "tier_0": (
        "Write a teaser line for the Basic Pack — 10 USDT, called 'The Survivors'. "
        "These tokens passed basic safety filters. They're alive but unattended. "
        "Tone: cheap ticket, judge for yourself, no promises."
    ),
    "tier_1": (
        "Write a teaser line for the Elite Chest — 20 USDT, called 'The Builders'. "
        "These tokens have devs still committing code and real community activity. "
        "Tone: someone is still building in the dark, curious why."
    ),
    "tier_2": (
        "Write a teaser line for the Mythic Crate — 30 USDT, called 'The Phoenixes'. "
        "Sophia's personal stamp. Multi-signal convergence. If anything in the ruins "
        "ever recovers, it's probably on this list. "
        "Tone: forensic conviction, zero hype, subtle weight."
    ),
    "connected": (
        "Write a brief line for a user who just connected their wallet and is ready to dig. "
        "Tone: you acknowledge their arrival like a graveyard guide acknowledging a new visitor."
    ),
    "disconnected": (
        "Write a brief farewell for a user who just disconnected. "
        "Tone: cold, understated, but not unfriendly. The ruins will still be here."
    ),
}


def _client_instance() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


@router.get("/config")
async def get_config():
    """Return public frontend config values read from .env."""
    return {"sophia_interval": settings.sophia_interval}


@router.get("/dialogue")
async def get_dialogue(context: str = "welcome"):
    if context not in CONTEXT_PROMPTS:
        context = "welcome"

    client = _client_instance()

    try:
        # Step 1: generate with haiku (fast, cheap)
        raw = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=80,
            system=SOPHIA_SYSTEM,
            messages=[{"role": "user", "content": CONTEXT_PROMPTS[context]}],
        )
        raw_text = raw.content[0].text.strip()

        # Step 2: crisp it up with sonnet
        polished = await client.messages.create(
            model=settings.humanize_model,
            max_tokens=80,
            system=HUMANIZE_SYSTEM,
            messages=[{"role": "user", "content": raw_text}],
        )
        final = polished.content[0].text.strip()

        logger.info(f"[ai] context={context!r} → {final!r}")
        return {"text": final}

    except Exception as exc:
        logger.warning(f"[ai] API error (context={context!r}): {exc}")
        return {"text": None}
