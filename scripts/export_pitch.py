"""
Generate Meme Scavenger hackathon pitch PDF (English + Chinese).
Output: meme_scavenger_pitch.pdf (desktop)
"""
import os
from fpdf import FPDF

FONT_REGULAR = r"C:\Windows\Fonts\msyh.ttc"    # Microsoft YaHei — supports CJK + Latin
FONT_BOLD    = r"C:\Windows\Fonts\msyhbd.ttc"
OUT_PATH     = os.path.join(os.path.expanduser("~"), "Desktop", "meme_scavenger_pitch.pdf")

GREEN  = (57, 255, 20)
DIM    = (120, 120, 120)
WHITE  = (255, 255, 255)
BLACK  = (10, 10, 18)
ACCENT = (255, 189, 51)


class PitchPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YaHei",  "",  FONT_REGULAR)
        self.add_font("YaHei",  "B", FONT_BOLD)
        self.set_auto_page_break(auto=True, margin=20)

    # ── helpers ──────────────────────────────────────────────────────────────
    def set_color(self, rgb):
        self.set_text_color(*rgb)

    def h1(self, text):
        self.ln(6)
        self.set_font("YaHei", "B", 20)
        self.set_color(GREEN)
        self.multi_cell(0, 10, text, align="L")
        self.ln(2)

    def h2(self, text):
        self.ln(4)
        self.set_font("YaHei", "B", 13)
        self.set_color(ACCENT)
        self.multi_cell(0, 8, text, align="L")
        self.ln(1)

    def h3(self, text):
        self.ln(3)
        self.set_font("YaHei", "B", 11)
        self.set_color(GREEN)
        self.multi_cell(0, 7, text, align="L")

    def body(self, text, indent=0):
        self.set_font("YaHei", "", 10)
        self.set_color(WHITE)
        if indent:
            self.set_x(self.get_x() + indent)
        self.multi_cell(0, 6, text, align="L")
        self.ln(1)

    def quote(self, text):
        self.ln(2)
        self.set_font("YaHei", "B", 11)
        self.set_color(DIM)
        self.set_x(20)
        self.multi_cell(0, 7, f"❝  {text}  ❞", align="L")
        self.ln(2)

    def bullet(self, items):
        for item in items:
            self.set_font("YaHei", "", 10)
            self.set_color(WHITE)
            self.set_x(20)
            self.multi_cell(0, 6, f"• {item}", align="L")
        self.ln(1)

    def divider(self):
        self.ln(3)
        self.set_draw_color(*GREEN)
        self.set_line_width(0.4)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def kv_table(self, headers, rows):
        col_w = (self.w - self.l_margin - self.r_margin) / len(headers)
        # header row
        self.set_font("YaHei", "B", 9)
        self.set_fill_color(30, 30, 50)
        self.set_color(GREEN)
        for h in headers:
            self.cell(col_w, 8, h, border=0, fill=True, align="C")
        self.ln()
        # data rows
        for row in rows:
            self.set_font("YaHei", "", 9)
            self.set_color(WHITE)
            for i, cell in enumerate(row):
                color = GREEN if i == 0 else WHITE
                self.set_color(color)
                self.cell(col_w, 7, cell, border=0, align="C")
            self.ln()
        self.ln(2)

    def cover_page(self, title, subtitle, tagline, lang_label):
        self.add_page()
        self.set_fill_color(*BLACK)
        self.rect(0, 0, self.w, self.h, "F")

        self.ln(30)
        self.set_font("YaHei", "B", 28)
        self.set_color(GREEN)
        self.cell(0, 14, title, align="C")
        self.ln(12)

        self.set_font("YaHei", "", 14)
        self.set_color(ACCENT)
        self.cell(0, 8, subtitle, align="C")
        self.ln(16)

        self.set_font("YaHei", "B", 11)
        self.set_color(DIM)
        self.multi_cell(0, 8, tagline, align="C")
        self.ln(10)

        self.set_font("YaHei", "", 9)
        self.set_color(DIM)
        self.cell(0, 6, lang_label, align="C")

    def section_page(self, label):
        """Full-page section divider."""
        self.add_page()
        self.set_fill_color(*BLACK)
        self.rect(0, 0, self.w, self.h, "F")
        self.ln(80)
        self.set_font("YaHei", "B", 22)
        self.set_color(GREEN)
        self.cell(0, 12, label, align="C")

    def content_page(self):
        self.add_page()
        self.set_fill_color(*BLACK)
        self.rect(0, 0, self.w, self.h, "F")
        self.set_margins(20, 20, 20)
        self.set_y(20)


# ── Build PDF ─────────────────────────────────────────────────────────────────

pdf = PitchPDF()

# ════════════════════════════════════════════════════════════
#  COVER
# ════════════════════════════════════════════════════════════
pdf.cover_page(
    "MEME SCAVENGER",
    "Hackathon Project Pitch  ·  AI Consumer Apps",
    "The ruins of BSC hold more value than most dare admit.\nWe built an AI agent that finds what survived.",
    "English · 中文  |  BNB Smart Chain  |  Powered by Anthropic Claude"
)

# ════════════════════════════════════════════════════════════
#  ENGLISH VERSION
# ════════════════════════════════════════════════════════════
pdf.section_page("ENGLISH VERSION")

# — Problem —
pdf.content_page()
pdf.h1("The Problem")
pdf.divider()

pdf.h2("1. Discovery Gap")
pdf.body(
    "Four.meme's REST API has a structural blind spot: an entire class of graduated tokens "
    "(listType=None) is completely invisible to any API query. These tokens only exist on-chain. "
    "Some carry millions in 24h volume — yet no standard tooling can surface them."
)

pdf.h2("2. Access Friction")
pdf.body(
    "Even when users find graduated tokens, assembling a curated basket requires multiple wallet "
    "transactions, manual research, and exposure to rug-pull risk with zero prior filtering. "
    "Ordinary users have no viable entry point."
)

# — Solution —
pdf.content_page()
pdf.h1("The Solution")
pdf.divider()
pdf.quote("Meme Scavenger is an on-chain archaeological platform.")
pdf.bullet([
    "SCAN   — eth_getLogs on Four.meme's TokenManager2 contract (0x5c952063) captures every graduation event, including API-invisible ones",
    "ARCHIVE — 13,000+ graduated tokens with volume, holder count, social links",
    "PACKAGE — Blind-box packs (Basic 10 USDT / Elite 20 USDT / Mythic 30 USDT)",
    "DELIVER — One user signature. Server hot-wallet executes PancakeSwap swaps, tokens arrive directly in buyer's wallet",
])
pdf.body(
    "AI agent Sophia (built on Anthropic Claude) guides users with cold, forensic commentary — "
    "no hype, no price predictions. Just archaeology."
)

# — Key Features —
pdf.content_page()
pdf.h1("Key Features")
pdf.divider()

pdf.h3("🔍  Novel Chain Scanner")
pdf.body(
    "Reverse-engineered the LiquidityAdded event signature (keccak256 of the official ABI) from "
    "TokenManager2. Scanned from block 37,500,000 to present. Discovered 11,730 tokens the API "
    "cannot see — the only known solution covering this token population."
)

pdf.h3("🤖  AI Agent — Sophia")
pdf.body(
    "Claude-powered contextual dialogue for every user interaction: connect, buy, error, rare find. "
    "Persona: cold, forensic, anti-hype. She reports facts. Users decide what they mean."
)

pdf.h3("💱  Server-Side Swap Delivery")
pdf.body(
    "User signs one transaction (USDT approve → contract buy()). Hot wallet executes all "
    "PancakeSwap swaps with `to = user_wallet` — tokens route directly without touching the hot "
    "wallet's output balance. No additional signatures. No EOA approval warnings."
)

pdf.h3("📡  Real-Time Live Feed")
pdf.body("On-chain events, Twitter mentions and DEX activity stream live via BSC RPC polling + Twitter API.")

pdf.h3("🗃️  Public Data Archive")
pdf.body("Free REST API exposing 13,000+ tokens, filterable by label, volume, holders, launch time.")

# — Differentiation —
pdf.content_page()
pdf.h1("What Makes This Different")
pdf.divider()
pdf.kv_table(
    ["Feature", "Existing Tools", "Meme Scavenger"],
    [
        ["Token discovery",     "API only",          "API + direct chain scan"],
        ["API-invisible tokens","✗  Not covered",    "✓  11,730 discovered"],
        ["Delivery mechanism",  "User: N swaps",     "Server delivers, 1 signature"],
        ["Curation filter",     "None / manual",     "Graduated filter + AI"],
        ["Data openness",       "Closed",            "Public REST API"],
    ]
)

pdf.h1("Traction")
pdf.divider()
pdf.bullet([
    "13,000+  graduated tokens archived across two token populations",
    "11,730   tokens discovered exclusively via on-chain scanning",
    "Live on BSC Mainnet — real USDT transactions",
    "Scan coverage: block 37.5M → present  (April 2024 → now)",
])

# — Tech Stack —
pdf.content_page()
pdf.h1("Technical Architecture")
pdf.divider()
pdf.body(
    "Python 3.10  ·  FastAPI  ·  web3.py  ·  MSSQL  ·  ethers.js v6\n"
    "Anthropic Claude API  ·  PancakeSwap V2  ·  BSC Mainnet\n"
    "Deployment: Windows Server  ·  IIS  ·  Waitress WSGI"
)
pdf.ln(2)
pdf.set_font("YaHei", "", 9)
pdf.set_color(DIM)
ascii_arch = """\
  [ Frontend: Vanilla JS + ethers.js v6 ]
            |   REST API
  [ FastAPI Backend ]
      |                   |
  [ Chain Scanner ]  [ Demo Swap Service ]
  eth_getLogs BSC     web3.py hot wallet
      |                   |     PancakeSwap V2
  [ MSSQL Database ]
  graduated_tokens · purchases · scan_state
      |
  [ Anthropic Claude  (Sophia AI) ]
"""
for line in ascii_arch.strip().split("\n"):
    pdf.set_x(22)
    pdf.cell(0, 5, line)
    pdf.ln()

# — Vision —
pdf.content_page()
pdf.h1("Vision")
pdf.divider()
pdf.body(
    "The meme economy is not going away — it is getting harder to navigate. "
    "Meme Scavenger is infrastructure for the next wave: a discovery layer that surfaces "
    "what actually graduated, packages it accessibly, and delivers it trustlessly. "
    "The blind-box mechanic is the entry point. The archive and public API are the moat."
)
pdf.ln(4)
pdf.quote("Most of what's here flatlined months ago. A few still have a pulse.\nWe'll let you decide which.")


# ════════════════════════════════════════════════════════════
#  CHINESE VERSION
# ════════════════════════════════════════════════════════════
pdf.section_page("中文版本")

# — 问题 —
pdf.content_page()
pdf.h1("问题")
pdf.divider()

pdf.h2("1. 发现盲区")
pdf.body(
    "Four.meme 官方 REST API 存在结构性缺陷——有一整类毕业代币（listType=None）对任何 API 查询完全不可见。"
    "这些代币只存在于链上，其中不乏 24 小时交易量达数百万美元的项目，但现有工具无法发现它们。"
)

pdf.h2("2. 访问门槛")
pdf.body(
    "即便用户找到了这些代币，购买一篮子组合仍需要多次钱包操作、手动调研，且没有任何防 rug 的前置过滤机制。"
    "普通用户根本无从下手。"
)

# — 解决方案 —
pdf.content_page()
pdf.h1("解决方案")
pdf.divider()
pdf.quote("Meme Scavenger 是一个链上考古平台。")
pdf.bullet([
    "扫链 — 通过 eth_getLogs 监听 Four.meme 官方 TokenManager2 合约（0x5c952063），捕获每一个毕业事件，包括 API 无法发现的",
    "归档 — 建立 13,000+ 毕业代币数据库，附带交易量、持有人数、社交链接等完整元数据",
    "打包 — 盲盒形式（基础包 10 USDT / 精英箱 20 USDT / 神话箱 30 USDT）",
    "直达 — 用户只需签名一次，服务器热钱包通过 PancakeSwap 完成多笔 Swap，代币直接发送到用户钱包",
])
pdf.body(
    "AI 探员 Sophia（基于 Anthropic Claude 构建）以冷静、法医式的语言风格全程引导用户——不造势、不吹牛，只汇报链上事实。"
)

# — 核心功能 —
pdf.content_page()
pdf.h1("核心功能")
pdf.divider()

pdf.h3("🔍  独创链上扫描器")
pdf.body(
    "通过逆向工程 Four.meme 官方合约的 LiquidityAdded 事件签名，从第 37,500,000 区块扫描至今，"
    "发现了 11,730 个 API 完全无法查询到的毕业代币。这是目前已知唯一能覆盖这一代币群体的方案。"
)

pdf.h3("🤖  AI 探员 Sophia")
pdf.body(
    "基于 Anthropic Claude 构建，为每个用户行为生成上下文感知的对话——连接钱包、购买、网络错误、发现稀有代币。"
    "她不预测涨跌，只陈述链上事实。"
)

pdf.h3("💱  服务端 Swap 一键交付")
pdf.body(
    "用户只需签署一笔交易（USDT 授权 → 合约 buy()）。服务器热钱包随即在 PancakeSwap 上执行所有 Swap，"
    "并通过 to 参数将代币直接路由到用户钱包——无需额外签名，无 EOA 授权警告。"
)

pdf.h3("📡  实时链上直播流")
pdf.body("链上事件、Twitter 提及、DEX 动态实时流入 Live Feed，通过 BSC RPC 轮询与 Twitter API 驱动。")

pdf.h3("🗃️  公开数据归档")
pdf.body("免费 REST API，开放 13,000+ 代币完整元数据，支持按标签、交易量、持有人数、上线时间过滤。")

# — 差异化 —
pdf.content_page()
pdf.h1("差异化对比")
pdf.divider()
pdf.kv_table(
    ["维度", "市面现有方案", "Meme Scavenger"],
    [
        ["代币发现方式",    "仅依赖 API",       "API + 直接链上扫描"],
        ["API 盲区代币",   "✗ 无法覆盖",       "✓ 已发现 11,730 个"],
        ["代币交付方式",    "用户自行多次 Swap", "服务端执行，1 次签名"],
        ["前置筛选机制",    "无 / 手动",        "毕业过滤 + AI 评级"],
        ["数据开放性",     "封闭",             "公开 REST API"],
    ]
)

pdf.h1("项目进展")
pdf.divider()
pdf.bullet([
    "已归档 13,000+ 毕业代币，覆盖两类代币群体",
    "11,730 个代币通过链上扫描独家发现（Four.meme API 不可见）",
    "已在 BSC 主网上线，支持真实 USDT 交易",
    "扫描覆盖范围：第 37.5M 区块至今（约 2024 年 4 月至今）",
])

# — 技术架构 —
pdf.content_page()
pdf.h1("技术架构")
pdf.divider()
pdf.body(
    "Python 3.10  ·  FastAPI  ·  web3.py  ·  MSSQL  ·  ethers.js v6\n"
    "Anthropic Claude API  ·  PancakeSwap V2  ·  BSC 主网\n"
    "部署环境：Windows Server  ·  IIS  ·  Waitress WSGI"
)

# — 愿景 —
pdf.content_page()
pdf.h1("愿景")
pdf.divider()
pdf.body(
    "Meme 经济不会消失，只会越来越难以导航。Meme Scavenger 是下一波浪潮的基础设施——"
    "一个发现层，把真正毕业的代币挖出来，以用户友好的方式打包，以链上可验证的方式交付。"
    "盲盒是切入点，归档数据库和公开 API 是护城河。"
)
pdf.ln(4)
pdf.quote("大多数废墟里的东西早已死透。少数还有心跳。\n我们帮你找到那些。")


# ── Save ─────────────────────────────────────────────────────────────────────
pdf.output(OUT_PATH)
print(f"PDF saved → {OUT_PATH}")
