# 🪦 MEME SCAVENGE AGENT

> *"They called it dead. I call it dormant."*

A Web3 loot-box experience built on BNB Smart Chain. An AI agent named **Sophia** — the Graveyard Whisperer — continuously scans thousands of near-zero meme tokens on BSC, sifts through the ruins, and curates a selection of tokens still showing signs of life. Users pay via USDT and receive a randomly selected meme token delivered directly to their wallet.

---

## 🎮 How It Works

1. User connects their BSC wallet (MetaMask, OKX, Trust, Binance Wallet)
2. Sophia speaks — AI-generated commentary on the token graveyard
3. User picks a tier (Basic Pack / Elite Chest / Mythic Crate) and pays via USDT
4. Backend hot wallet swaps the full amount into a randomly selected demo token on PancakeSwap
5. Tokens are delivered directly to the user's wallet
6. Share your find as a generated image

---

## 💰 Business Model

Users pay USDT to receive a randomly selected meme token. The platform charges a **5% fee** on every purchase — retained by the MemeScavenger smart contract at the point of payment. The remaining 95% is used to execute the token swap via PancakeSwap and deliver the tokens directly to the user's wallet.

| Tier | User Pays | Platform Fee (5%) | Swapped to Token |
|---|---|---|---|
| Basic Pack | 10 USDT | 0.50 USDT | 9.50 USDT |
| Elite Chest | 20 USDT | 1.00 USDT | 19.00 USDT |
| Mythic Crate | 30 USDT | 1.50 USDT | 28.50 USDT |

Simple, transparent, on-chain.

---

## 🧬 Core Product Logic — Three-Dimensional Resilience Model (60/30/10)

> We don't look at short-term price. We look at the **vital signs** of core consensus.

The scoring engine evaluates every token across three dimensions, weighted to reflect what actually predicts recovery in dead meme markets:

### 60% — Social Persistence
Continuous 24/7 monitoring via **X (Twitter) API Filtered Stream**. Raw social volume means nothing — the AI layer (Claude + GLM-5) distinguishes bot activity and paid shills from genuine community conviction. The signal we hunt: communities still producing content and iterating on narrative *after* a 95% drawdown. That stubbornness is rare. When it exists, it means something.

### 30% — On-Chain Conviction
Deep chain analysis focused on the **Top 20 core holding addresses** per token. Wash trading and volume manipulation are filtered out. The only metric that matters: are whales accumulating during the ruins period? If price is in the basement and smart money is quietly stacking — the system assigns maximum financial weight.

### 10% — Human / AI Intuition (Cultural Aesthetic)
Qualitative assessment of the token's IP uniqueness, nostalgia factor, and secondary creation potential. AI-assisted scoring asks one question: *Is this story worth retelling?* Memes with strong cultural DNA resurface. Generic ones don't.

---

## 🧱 Tech Stack

### Backend
| | |
|---|---|
| **FastAPI** | Python async web framework |
| **Uvicorn** | ASGI server (production) |
| **pyodbc** | Microsoft SQL Server connector |
| **MSSQL** | Primary database (purchases, tokens, scan state) |
| **web3.py** | BSC on-chain interaction (swap execution, log scanning) |
| **httpx** | Async HTTP client (Four.meme API, DexScreener scraping) |
| **pydantic-settings** | Environment-based configuration |

### Frontend
| | |
|---|---|
| **Vanilla JS** | Zero-framework frontend |
| **ethers.js v6** | Wallet connection and contract interaction |
| **HTML5 Canvas** | Client-side share image generation |
| **Press Start 2P** | Pixel-art typography (Google Fonts) |
| **CSS animations** | Particle bursts, glows, scanline overlay |

### Blockchain
| | |
|---|---|
| **BNB Smart Chain** | Target network (Chain ID 56) |
| **PancakeSwap V2** | DEX used for token swaps |
| **USDT (BEP-20)** | Payment token |
| **MemeScavenger Contract** | Custom Solidity contract handling tier pricing and purchase events |

### Infrastructure
| | |
|---|---|
| **Windows Server + IIS** | Hosting (reverse proxy to Uvicorn) |
| **IIS URL Rewrite + ARR** | Reverse proxy layer |

---

## 🤖 AI — Sophia (The Graveyard Whisperer)

Sophia is the on-screen AI agent persona powered by **Anthropic Claude**.

### Dual-model pipeline
Every dialogue line goes through two Claude calls:

| Step | Model | Role |
|---|---|---|
| **Generate** | Claude Haiku | Fast, cheap — produces a raw line in Sophia's persona |
| **Polish** | Claude Sonnet | Crisps the line — tightens tone, removes filler |

### Persona
Sophia is a chain archaeologist. Cold, patient, sardonic. She scans BSC ruins every day looking for tokens still showing a heartbeat — dev commits, real community activity, non-zero on-chain signals. She never hypes. Never uses 🚀. Never says "100x". She speaks like a forensic analyst who moonlights as a dark-web archivist.

### Token Discovery — On-Chain Scanner
Beyond Sophia's dialogue, the backend runs an autonomous BSC chain scanner:

- Monitors the **Four.meme TokenManager2 contract** (`0x5c952063c7fc8610FFDB798152D69F0B9550762b`)
- Listens for `LiquidityAdded` events (topic `0xc18aa711...`)
- Discovers `listType=None` tokens invisible to the Four.meme public API
- Supplements the API scraper (NOR_DEX + BIN_DEX tokens)
- Persists scan cursor in DB — each run only fetches new blocks

---

## 🗂 Project Structure

```
meme-scavenger/
├── app/
│   ├── routes/          # FastAPI routers (purchases, AI, demo, live feed)
│   ├── scraper/         # Four.meme API + BSC on-chain scanner
│   ├── services/        # Demo swap execution (PancakeSwap hot wallet)
│   ├── config.py        # pydantic-settings (.env loader)
│   ├── database.py      # pyodbc connection manager
│   └── main.py          # FastAPI app entry
├── frontend/
│   ├── index.html
│   ├── static/
│   │   ├── css/app.css
│   │   └── js/
│   │       ├── app.js       # Main frontend logic
│   │       └── contract.js  # ABI + contract addresses
│   └── images/
├── db/migrations/       # SQL migration scripts
├── scripts/             # Standalone runner scripts
├── server.py            # Production entry (Uvicorn)
├── start.bat            # Windows start script
└── web.config           # IIS reverse proxy config
```

---

## ⚙️ Configuration (.env)

```env
# Database
MSSQL_SERVER=localhost
MSSQL_DATABASE=meme_scavenger
MSSQL_USER=
MSSQL_PASSWORD=
MSSQL_DRIVER=18          # 17 or 18
MSSQL_ENCRYPT=no

# App
APP_HOST=127.0.0.1
APP_PORT=8000

# AI
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
HUMANIZE_MODEL=claude-sonnet-4-5

# BSC
BSC_CONTRACT_ADDRESS=0x...
BSC_RPC_URL=https://bsc-dataseed.binance.org/

# Demo Mode Hot Wallet
HOT_WALLET_ADDRESS=0x...
HOT_WALLET_PRIVATE_KEY=0x...

# Platform Fee
PLATFORM_FEE_PCT=5.0        # percentage retained per purchase (default: 5%)
```

---

## 🚀 Quick Start (Local)

```bash
pip install -r requirements.txt
pip install uvicorn
python server.py
```

Open `http://localhost:8000`

---

## 🪟 Production Deployment (Windows Server + IIS)

1. Install **IIS ARR 3.0** + **URL Rewrite 2.1**
2. Enable ARR proxy: IIS Manager → Server → Application Request Routing Cache → Server Proxy Settings → **Enable proxy**
3. Point IIS website physical path to the project root (`web.config` handles reverse proxy)
4. Run `start.bat` or register with **NSSM** as a Windows Service for auto-start
5. Configure SSL via Win-ACME (Let's Encrypt) or your own certificate

---

## 📜 License

MIT
