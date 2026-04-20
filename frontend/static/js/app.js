// ── State ──
let walletAddress = null;
let activeProvider = null;

const BSC_CHAIN_ID = '0x38'; // BSC Mainnet = 56

const BSC_PARAMS = {
  chainId: BSC_CHAIN_ID,
  chainName: 'BNB Smart Chain',
  nativeCurrency: { name: 'BNB', symbol: 'BNB', decimals: 18 },
  rpcUrls: ['https://bsc-dataseed.binance.org/'],
  blockExplorerUrls: ['https://bscscan.com/'],
};

// Supported wallets — provider getter + install URL
const SUPPORTED_WALLETS = [
  {
    id: 'metamask',
    name: 'MetaMask',
    icon: 'https://upload.wikimedia.org/wikipedia/commons/3/36/MetaMask_Fox.svg',
    getProvider: () => {
      if (window.ethereum?.isMetaMask) return window.ethereum;
      const p = window.ethereum?.providers?.find(p => p.isMetaMask);
      return p || null;
    },
    installUrl: 'https://metamask.io/download/',
  },
  {
    id: 'okx',
    name: 'OKX Wallet',
    icon: 'https://static.okx.com/cdn/assets/imgs/247/58E63FEA47A2B7D7.png',
    getProvider: () => window.okxwallet || null,
    installUrl: 'https://www.okx.com/web3',
  },
  {
    id: 'trust',
    name: 'Trust Wallet',
    icon: 'https://trustwallet.com/assets/images/media/assets/TWT.png',
    getProvider: () => {
      if (window.trustwallet) return window.trustwallet;
      if (window.ethereum?.isTrust) return window.ethereum;
      const p = window.ethereum?.providers?.find(p => p.isTrust);
      return p || null;
    },
    installUrl: 'https://trustwallet.com/download',
  },
  {
    id: 'binance',
    name: 'Binance Wallet',
    icon: 'https://public.bnbstatic.com/image/pgc/202405/47e39b10aa6b09d35278dcaa4f8baa4c.png',
    getProvider: () => window.BinanceChain || null,
    installUrl: 'https://www.bnbchain.org/en/binance-wallet',
  },
];

const TIER_PRICES = [10, 20, 30];

// Static fallback lines — used while AI fetch is pending or if API is unavailable.
// Tone must match Sophia's persona: cold, forensic, no hype, no rockets.
const LINES = [
  "Most of what's here flatlined months ago. A few still have a pulse. I'll let you decide which.",
  "The Survivors. Passed basic filters. Nobody's watering them — but they haven't been buried yet.",
  "The Builders. Dev committed code three days ago. I don't know why. That's exactly why it's interesting.",
  "The Phoenixes. My personal list. Not financial advice. Just forensic evidence.",
];

// ── AI Dialogue ──
const _dlgCache = {};

// Tracks whether Sophia is mid-transaction (suppress auto-tick during buy flow)
let _sophiaBusy = false;

async function fetchDialogue(context) {
  if (_dlgCache[context]) return _dlgCache[context];
  try {
    const res = await fetch(`/api/ai/dialogue?context=${context}`);
    if (res.ok) {
      const { text } = await res.json();
      if (text) { _dlgCache[context] = text; return text; }
    }
  } catch {}
  return null;
}

async function aiTypeText(context, fallback) {
  const text = await fetchDialogue(context);
  typeText(text || fallback);
}

// ── Auto-tick: Sophia speaks every N seconds ──
const _AUTO_CONTEXTS = ['welcome', 'tier_0', 'tier_1', 'tier_2'];
const _AUTO_FALLBACKS = [LINES[0], LINES[1], LINES[2], LINES[3]];
let _autoIdx = 0;  // cycles through contexts so responses vary

async function _startSophiaTimer(intervalSec) {
  setInterval(async () => {
    if (_sophiaBusy) return;                    // don't interrupt buy flow
    // Evict cache so Claude generates a fresh line each tick
    const ctx = _AUTO_CONTEXTS[_autoIdx % _AUTO_CONTEXTS.length];
    delete _dlgCache[ctx];
    await aiTypeText(ctx, _AUTO_FALLBACKS[_autoIdx % _AUTO_FALLBACKS.length]);
    _autoIdx++;
  }, intervalSec * 1000);
}

// ── Wallet helpers ──
function shortAddr(addr) {
  return addr.slice(0, 6) + '...' + addr.slice(-4);
}

function setWalletUI(addr, onBsc) {
  const btn   = document.getElementById('wallet-btn');
  const label = document.getElementById('wallet-label');
  const badge = document.getElementById('network-badge');

  walletAddress = addr;

  // Remove existing hover listeners before re-adding
  btn.onmouseenter = null;
  btn.onmouseleave = null;

  if (!addr) {
    btn.classList.remove('wallet-connected', 'wallet-wrong-network');
    label.textContent = 'Connect Wallet';
    badge.style.display = 'none';
    return;
  }

  const addrShort = shortAddr(addr);
  label.textContent = addrShort;
  badge.style.display = 'flex';

  if (onBsc) {
    btn.classList.add('wallet-connected');
    btn.classList.remove('wallet-wrong-network');
    badge.textContent = 'BSC';
    // Hover: show DISCONNECT hint
    btn.onmouseenter = () => { label.textContent = 'DISCONNECT'; };
    btn.onmouseleave = () => { label.textContent = addrShort; };
  } else {
    btn.classList.remove('wallet-connected');
    btn.classList.add('wallet-wrong-network');
    badge.textContent = 'Wrong Network';
  }
}

async function switchToBsc(provider) {
  const p = provider || activeProvider;
  try {
    await p.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: BSC_CHAIN_ID }] });
  } catch (err) {
    if (err.code === 4902) {
      await p.request({ method: 'wallet_addEthereumChain', params: [BSC_PARAMS] });
    } else {
      throw err;
    }
  }
}

// ── Wallet picker modal ──
function openWalletModal() {
  const list = document.getElementById('wallet-list');
  list.innerHTML = '';

  SUPPORTED_WALLETS.forEach(w => {
    const provider = w.getProvider();
    const installed = !!provider;

    const el = document.createElement('div');
    el.className = 'wallet-option' + (installed ? ' installed' : '');
    el.innerHTML = `
      <div class="wallet-option-icon">
        <img src="${w.icon}" alt="${w.name}" style="width:36px;height:36px;border-radius:8px;" onerror="this.style.display='none'">
      </div>
      <div class="wallet-option-info">
        <div class="wallet-option-name">${w.name}</div>
        <div class="wallet-option-status">${installed ? '● DETECTED' : 'Not installed'}</div>
      </div>`;

    el.onclick = () => {
      document.getElementById('wallet-modal').style.display = 'none';
      if (installed) {
        doConnect(provider);
      } else {
        window.open(w.installUrl, '_blank');
      }
    };
    list.appendChild(el);
  });

  document.getElementById('wallet-modal').style.display = 'flex';
}

function closeWalletModal(e) {
  if (e.target === document.getElementById('wallet-modal')) {
    document.getElementById('wallet-modal').style.display = 'none';
  }
}

// ── Connect wallet ──
function connectWallet() {
  // Already connected — disconnect
  if (walletAddress) {
    if (activeProvider) {
      activeProvider.removeListener?.('accountsChanged', onAccountsChanged);
      activeProvider.removeListener?.('chainChanged', onChainChanged);
    }
    activeProvider = null;
    setWalletUI(null, false);
    aiTypeText("disconnected", "Disconnected. The ruins will still be here when you get back.");
    return;
  }
  openWalletModal();
}

async function doConnect(provider) {
  try {
    const accounts = await provider.request({ method: 'eth_requestAccounts' });
    const chainId  = await provider.request({ method: 'eth_chainId' });
    const onBsc    = chainId === BSC_CHAIN_ID;

    activeProvider = provider;
    setWalletUI(accounts[0], onBsc);

    if (!onBsc) {
      typeText("Wrong network. Switching you to BSC — ruins don't run on testnets.");
      await switchToBsc(provider);
    } else {
      aiTypeText("connected", "Wallet confirmed. The ruins are open. Take your time — dead tokens don't run.");
    }

    provider.on('accountsChanged', onAccountsChanged);
    provider.on('chainChanged', onChainChanged);
  } catch (err) {
    if (err.code === 4001) {
      typeText("Connection cancelled. The graveyard doesn't go anywhere.");
    } else {
      typeText("Wallet error. Check your connection and try again.");
      console.error(err);
    }
  }
}

// ── Named listeners (needed for removeListener on disconnect) ──
function onAccountsChanged(accounts) {
  if (!accounts.length) {
    activeProvider = null;
    setWalletUI(null, false);
    aiTypeText("disconnected", "Signal lost. The ruins will still be here when you reconnect.");
    return;
  }
  activeProvider.request({ method: 'eth_chainId' }).then(chainId => {
    setWalletUI(accounts[0], chainId === BSC_CHAIN_ID);
  });
}

function onChainChanged(chainId) {
  if (!walletAddress) return;
  const onBsc = chainId === BSC_CHAIN_ID;
  setWalletUI(walletAddress, onBsc);
  if (!onBsc) {
    typeText("Wrong network detected. Click Wallet to return to BSC — that's where the ruins are.");
  } else {
    typeText("Back on BSC. Heartbeat detected. Ready when you are.");
  }
}

function initWalletListeners() { /* listeners attached per-provider in doConnect */ }

// ── Confirm dialog ──
const TIER_INFO = [
  { name: 'Basic Pack',    img: '/images/n1.png', price: '10 USDT', desc: 'A mystery bag from the ruins.\nCommon finds, rare surprises.',    cls: 'tier-0' },
  { name: 'Elite Chest',   img: '/images/n2.png', price: '20 USDT', desc: 'Excavated from deep in the\ncyber ruins. Rare odds await.',      cls: 'tier-1' },
  { name: 'Mythic Crate',  img: '/images/n3.png', price: '30 USDT', desc: 'A legendary relic. Only the\nboldest dare open this crate.',      cls: 'tier-2' },
];

function buy(tier) {
  if (!walletAddress) {
    showWarningToast('Wallet Not Connected', 'Connect your wallet to continue →');
    setTimeout(() => connectWallet(), 600);
    return;
  }

  const info = TIER_INFO[tier];
  document.querySelector('.confirm-box').className = `confirm-box ${info.cls}`;
  const badge = document.getElementById('confirm-tier-badge');
  badge.textContent = info.name;
  badge.className = `confirm-tier-badge ${info.cls}`;
  document.getElementById('confirm-img').src    = info.img;
  document.getElementById('confirm-title').textContent = info.name;
  document.getElementById('confirm-price').textContent = info.price;
  document.getElementById('confirm-desc').textContent  = info.desc;
  document.getElementById('confirm-btn-ok').onclick = () => {
    document.getElementById('confirm-modal').style.display = 'none';
    doBuy(tier);
  };
  document.getElementById('confirm-modal').style.display = 'flex';
}

function closeConfirmModal(e) {
  if (e.target === document.getElementById('confirm-modal'))
    document.getElementById('confirm-modal').style.display = 'none';
}

// ── Actual buy (called after confirm) ──
async function doBuy(tier) {
  try {
    if (!activeProvider) throw new Error("Wallet not connected.");
    const chainId = await activeProvider.request({ method: 'eth_chainId' });
    if (chainId !== BSC_CHAIN_ID) {
      typeText("Wrong network. The contract lives on BSC — click Wallet to switch.");
      return;
    }
    if (DEMO_MODE) {
      await doBuyDemo(tier);
    } else {
      await doBuyContract(tier);
    }
  } catch (err) {
    if (err.code === 4001 || err.code === 'ACTION_REJECTED') {
      typeText("Cancelled. The ruins will still be here when you're ready.");
    } else {
      typeText(`Error: ${err.message || 'Unknown error. Check console.'}`);
      console.error('[doBuy]', err);
    }
  }
}

// ── Demo Mode: pay via contract → backend delivers tokens to user wallet ──
// User approves USDT to the MemeScavenger *contract* (not an EOA — no scary warning).
// After the buy() tx confirms, our hot wallet swaps demo tokens and sends them directly.
async function doBuyDemo(tier) {
  const btns = document.querySelectorAll('.btn');
  btns.forEach(b => b.disabled = true);
  _sophiaBusy = true;
  await aiTypeText(`tier_${tier}`, LINES[tier + 1]);

  try {
    const ethersProvider = new ethers.BrowserProvider(activeProvider);
    const signer         = await ethersProvider.getSigner();
    const usdtContract   = new ethers.Contract(USDT_ADDRESS, USDT_ABI,  signer);
    const memeContract   = new ethers.Contract(CONTRACT_ADDRESS, MEME_ABI, signer);

    // 1 — Get price + demo token count in parallel
    const [price, demoTokens] = await Promise.all([
      memeContract.getPrice(tier),
      fetch('/api/fourmeme/demo-tokens').then(r => r.json()).catch(() => []),
    ]);
    const tokenCount = demoTokens.length || '?';

    // 2 — Check USDT balance
    typeText('Checking USDT balance…');
    const balance = await usdtContract.balanceOf(walletAddress);
    if (balance < price) {
      const have = parseFloat(ethers.formatUnits(balance, 18)).toFixed(2);
      const need = parseFloat(ethers.formatUnits(price,   18)).toFixed(2);
      typeText(`Insufficient USDT. Need ${need} USDT, wallet has ${have} USDT.`);
      return;
    }

    // 3 — Approve USDT to the contract (if allowance too low)
    const allowance = await usdtContract.allowance(walletAddress, CONTRACT_ADDRESS);
    if (allowance < price) {
      typeText('Approve USDT spend. Confirm in your wallet…');
      const approveTx = await usdtContract.approve(CONTRACT_ADDRESS, price);
      await approveTx.wait();
    }

    // 4 — Call contract buy() — USDT goes to contract, NOT to any personal wallet
    typeText('Confirm purchase in your wallet…');
    const buyTx = await memeContract.buy(tier);
    showWaitingModal(buyTx.hash);   // stays open until tokens delivered
    typeText('Payment sent. Waiting for BSC confirmation…');
    const receipt = await buyTx.wait();

    showTxSuccess(receipt.hash);
    updateWaitingModal(
      'PREPARING YOUR TOKENS',
      `Payment confirmed ✓<br>Swapping ${tokenCount} tokens on-chain…<br>This takes ~30 seconds.`,
    );
    typeText('Payment confirmed. Server is swapping your tokens…');

    // 5 — Tell backend to deliver demo tokens directly to user's wallet
    //       (purchase is recorded server-side inside /api/demo/deliver)
    const deliverRes = await fetch('/api/demo/deliver', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ wallet: walletAddress, tier, tx_hash: receipt.hash }),
    });
    hideWaitingModal();   // close only after delivery attempt

    if (!deliverRes.ok) {
      const e = await deliverRes.json().catch(() => ({ detail: 'Server error' }));
      throw new Error(e.detail || 'Token delivery failed — contact support with tx hash.');
    }
    const result = await deliverRes.json();

    // 6 — Show results
    const s = result.swaps[0];
    typeText(s?.success
      ? `Done — $${s.token.symbol} delivered to your wallet.`
      : `Swap failed. Contact support with your tx hash.`);
    showSwapResults(result.swaps, TIER_PRICES[tier]);

  } catch (err) {
    hideWaitingModal();
    if (err.code === 4001 || err.code === 'ACTION_REJECTED') {
      typeText("Cancelled. The ruins will still be here when you're ready.");
    } else {
      typeText(`Something went wrong: ${err.message}`);
      console.error('[doBuyDemo]', err);
    }
  } finally {
    btns.forEach(b => b.disabled = false);
    _sophiaBusy = false;
  }
}

// ── Original contract-based buy (non-demo mode) ──
async function doBuyContract(tier) {
  if (CONTRACT_ADDRESS === '0x0000000000000000000000000000000000000000') {
    typeText("Contract not deployed yet. Come back when the excavation site is ready.");
    return;
  }

  const btns = document.querySelectorAll('.btn');
  btns.forEach(b => b.disabled = true);
  _sophiaBusy = true;
  aiTypeText(`tier_${tier}`, LINES[tier + 1]);

  try {
    const ethersProvider = new ethers.BrowserProvider(activeProvider);
    const signer = await ethersProvider.getSigner();

    const usdtContract = new ethers.Contract(USDT_ADDRESS, USDT_ABI, signer);
    const memeContract = new ethers.Contract(CONTRACT_ADDRESS, MEME_ABI, signer);

    const price = await memeContract.getPrice(tier);

    const allowance = await usdtContract.allowance(walletAddress, CONTRACT_ADDRESS);
    if (allowance < price) {
      typeText("Requesting USDT approval. Confirm in your wallet to proceed.");
      const approveTx = await usdtContract.approve(CONTRACT_ADDRESS, price);
      await approveTx.wait();
      aiTypeText(`tier_${tier}`, LINES[tier + 1]);
    }

    typeText("Sending payment. Confirm in your wallet.");
    const buyTx = await memeContract.buy(tier);
    showWaitingModal(buyTx.hash);
    typeText("Transaction broadcast. Waiting for BSC confirmation.");
    const receipt = await buyTx.wait();
    hideWaitingModal();

    const tierNames = ['Basic Pack', 'Elite Chest', 'Mythic Crate'];
    typeText(`Payment confirmed. Opening your ${tierNames[tier]}. Let's see what survived.`);
    showTxSuccess(receipt.hash);

    try {
      const res = await fetch('/api/purchases', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          wallet_address: walletAddress,
          tier,
          price_u: TIER_PRICES[tier],
          tx_hash: receipt.hash,
        }),
      });
      if (res.ok) {
        const purchase = await res.json();
        const dropRes  = await fetch(`/api/purchases/${purchase.id}/drop`);
        const drop     = await dropRes.json();
        showDrop(drop);
      } else {
        showDrop(randomDrop(tier));
      }
    } catch {
      showDrop(randomDrop(tier));
    }

  } catch (err) {
    hideWaitingModal();
    if (err.code === 4001 || err.code === 'ACTION_REJECTED') {
      typeText("Transaction cancelled. The ruins will still be here when you're ready.");
    } else {
      typeText("Something went wrong in the ruins. Check your wallet and try again.");
      console.error(err);
    }
  } finally {
    btns.forEach(b => b.disabled = false);
    _sophiaBusy = false;
  }
}

// ── Demo swap results modal (single token) ──
function showSwapResults(results, totalUsdt) {
  const r   = results[0];   // always 1 token now
  const tok = r ? r.token : null;

  const logoHtml = tok?.img_url
    ? `<img src="${tok.img_url}" alt="${tok.symbol}" class="swap-solo-logo"
           onerror="this.outerHTML='<div class=\\'swap-logo-fallback swap-solo-logo\\'>🪙</div>'">`
    : `<div class="swap-logo-fallback swap-solo-logo">🪙</div>`;

  const statusHtml = r?.success
    ? `<div class="swap-solo-amount">+${r.received}</div>`
    : `<div class="swap-failed-msg">✗ Swap failed — no liquidity</div>`;

  const dexUrl   = tok?.address
    ? `https://dexscreener.com/bsc/${tok.address}`
    : null;
  const tierName = ['Basic Pack','Elite Chest','Mythic Crate'][
    document.querySelector && (() => {
      // recover tier from price
      if (totalUsdt === 10) return 0;
      if (totalUsdt === 20) return 1;
      return 2;
    })()
  ] || '';

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal-box swap-results-modal">
      <div class="modal-title">✦ SWAP COMPLETE ✦</div>
      <div class="swap-solo-card ${r?.success ? 'swap-ok' : 'swap-fail'}">
        <div class="swap-solo-logo-wrap">${logoHtml}</div>
        <div class="swap-solo-symbol">${tok ? '$' + tok.symbol : '—'}</div>
        <div class="swap-solo-name">${tok?.name || ''}</div>
        ${statusHtml}
      </div>
      <div class="swap-total-label">${totalUsdt} USDT → ${tok?.symbol || '?'}</div>
      <div class="swap-action-row">
        ${dexUrl ? `<button class="swap-btn swap-btn-analyze" onclick="window.open('${dexUrl}','_blank')">ANALYZE ↗</button>` : ''}
        <button class="swap-btn swap-btn-share" onclick="generateShareImage(${JSON.stringify(tok)}, '${r?.received || '?'}', ${totalUsdt})">SHARE</button>
        <button class="swap-btn swap-btn-done" onclick="this.closest('.modal-overlay').remove()">DONE</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
}

// ── Share image generator (Canvas) ──
async function generateShareImage(token, received, totalUsdt) {
  const W = 900, H = 450;
  const canvas = document.createElement('canvas');
  canvas.width  = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');

  // 1 — Draw share.png semi-transparent
  await new Promise(resolve => {
    const bg = new Image();
    bg.crossOrigin = 'anonymous';
    bg.onload = () => {
      ctx.globalAlpha = 0.38;
      ctx.drawImage(bg, 0, 0, W, H);
      ctx.globalAlpha = 1;
      resolve();
    };
    bg.onerror = resolve;
    bg.src = '/images/share.png';
  });

  // 2 — Dark overlay for readability
  ctx.fillStyle = 'rgba(6,6,16,0.62)';
  ctx.fillRect(0, 0, W, H);

  // 3 — Pixel grid pattern
  ctx.strokeStyle = 'rgba(57,255,20,0.06)';
  ctx.lineWidth = 1;
  for (let x = 0; x < W; x += 28) { ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,H); ctx.stroke(); }
  for (let y = 0; y < H; y += 28) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(W,y); ctx.stroke(); }

  // 4 — Token logo (circle)
  if (token?.img_url) {
    await new Promise(resolve => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        const cx = W / 2, cy = 185, r = 68;
        ctx.save();
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.clip();
        ctx.drawImage(img, cx - r, cy - r, r * 2, r * 2);
        ctx.restore();
        // Ring
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.strokeStyle = '#39FF14';
        ctx.lineWidth = 3;
        ctx.shadowColor = '#39FF14';
        ctx.shadowBlur = 12;
        ctx.stroke();
        ctx.shadowBlur = 0;
        resolve();
      };
      img.onerror = resolve;
      img.src = token.img_url;
    });
  }

  const cx = W / 2;

  // 5 — Site title (top)
  ctx.font = '14px "Press Start 2P", monospace';
  ctx.fillStyle = '#555';
  ctx.textAlign = 'center';
  ctx.letterSpacing = '3px';
  ctx.fillText('MEME SCAVENGE AGENT', cx, 44);

  // 6 — Token symbol (big green glow)
  ctx.font = 'bold 52px "Press Start 2P", monospace';
  ctx.fillStyle = '#39FF14';
  ctx.shadowColor = '#39FF14';
  ctx.shadowBlur = 24;
  ctx.fillText('$' + (token?.symbol || '?'), cx, 296);
  ctx.shadowBlur = 0;

  // 7 — Amount received
  ctx.font = '20px "Press Start 2P", monospace';
  ctx.fillStyle = '#ffffff';
  ctx.fillText('+' + received + ' tokens', cx, 340);

  // 8 — Bottom info bar
  const tierName = totalUsdt === 10 ? 'Basic Pack' : totalUsdt === 20 ? 'Elite Chest' : 'Mythic Crate';
  const dateStr  = new Date().toLocaleDateString('en-GB');
  ctx.font = '11px "Press Start 2P", monospace';
  ctx.fillStyle = '#444';
  ctx.fillText(tierName + '  ·  ' + totalUsdt + ' USDT  ·  ' + dateStr, cx, 400);

  // 9 — Green border
  ctx.strokeStyle = '#39FF14';
  ctx.lineWidth = 4;
  ctx.shadowColor = '#39FF14';
  ctx.shadowBlur = 16;
  ctx.strokeRect(6, 6, W - 12, H - 12);
  ctx.shadowBlur = 0;

  // 10 — Download
  const link = document.createElement('a');
  link.download = `meme-scavenger-${(token?.symbol || 'token').toLowerCase()}.png`;
  link.href = canvas.toDataURL('image/png');
  link.click();
}

// ── Warning toast ──
function showWarningToast(title, subtitle = '') {
  const existing = document.getElementById('warn-toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.id = 'warn-toast';
  toast.className = 'tx-toast warn-toast';
  toast.innerHTML = `
    <div class="tx-toast-icon">⚠️</div>
    <div class="tx-toast-body">
      <div class="tx-toast-title" style="color:#ff2244;text-shadow:0 0 8px #ff2244">${title}</div>
      ${subtitle ? `<div class="tx-toast-hash" style="color:#666">${subtitle}</div>` : ''}
    </div>`;
  document.body.appendChild(toast);

  setTimeout(() => toast.classList.add('tx-toast-hide'), 3000);
  setTimeout(() => toast.remove(), 3600);
}

// ── Waiting-for-confirmation modal ──
function showWaitingModal(txHash) {
  hideWaitingModal();
  const overlay = document.createElement('div');
  overlay.id = 'waiting-modal';
  overlay.className = 'modal-overlay waiting-overlay';
  const short = txHash ? txHash.slice(0, 10) + '…' + txHash.slice(-6) : '';
  overlay.innerHTML = `
    <div class="modal-box waiting-modal-box">
      <div class="waiting-spinner" id="waiting-spinner"></div>
      <div class="modal-title" id="waiting-title">WAITING FOR CONFIRMATION</div>
      <div class="waiting-subtext" id="waiting-subtext">
        Transaction broadcast to BSC.<br>Waiting for block confirmation…
      </div>
      ${short ? `<a class="waiting-hash" href="https://bscscan.com/tx/${txHash}" target="_blank">${short} ↗</a>` : ''}
      <button class="modal-close" style="margin-top:4px" onclick="hideWaitingModal()">CLOSE</button>
    </div>`;
  document.body.appendChild(overlay);
}

function updateWaitingModal(title, subtext) {
  const t = document.getElementById('waiting-title');
  const s = document.getElementById('waiting-subtext');
  if (t) t.textContent = title;
  if (s) s.innerHTML = subtext;
}

function hideWaitingModal() {
  const el = document.getElementById('waiting-modal');
  if (el) el.remove();
}

// ── Tx success toast ──
function showTxSuccess(txHash) {
  const existing = document.getElementById('tx-toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.id = 'tx-toast';
  toast.className = 'tx-toast';
  const short = txHash.slice(0, 10) + '...' + txHash.slice(-6);
  toast.innerHTML = `
    <div class="tx-toast-icon">✅</div>
    <div class="tx-toast-body">
      <div class="tx-toast-title">PAYMENT CONFIRMED</div>
      <a class="tx-toast-hash" href="https://bscscan.com/tx/${txHash}" target="_blank">${short} ↗</a>
    </div>`;
  document.body.appendChild(toast);

  // Auto-dismiss after 8s
  setTimeout(() => toast.classList.add('tx-toast-hide'), 8000);
  setTimeout(() => toast.remove(), 8600);
}

// ── Fallback drop when backend is offline ──
const TIER_DROPS_CLIENT = {
  0: [{token_symbol:'DOGE',rarity:'common'},{token_symbol:'SHIB',rarity:'common'},{token_symbol:'FLOKI',rarity:'common'}],
  1: [{token_symbol:'PEPE',rarity:'rare'},{token_symbol:'BONK',rarity:'rare'},{token_symbol:'WIF',rarity:'rare'}],
  2: [{token_symbol:'BRETT',rarity:'mythic'},{token_symbol:'MAGA',rarity:'mythic'},{token_symbol:'POPCAT',rarity:'mythic'}],
};
function randomDrop(tier) {
  const pool = TIER_DROPS_CLIENT[tier];
  return pool[Math.floor(Math.random() * pool.length)];
}

// ── Drop modal ──
function showDrop(drop) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal-box">
      <div class="modal-title">✦ YOU GOT ✦</div>
      <div class="modal-token">$${drop.token_symbol}</div>
      <div class="modal-rarity rarity-${drop.rarity}">${drop.rarity.toUpperCase()}</div>
      <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">CLAIM IT!</button>
    </div>`;
  document.body.appendChild(overlay);
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
}

// ── Card hover: continuous sparks + dialogue ──
let _burstTimer  = null;
const _PAL_KEYS  = ['gray', 'blue', 'gold'];

function hoverCard(tier, card) {
  // Continuous spark loop — stop any previous one first
  if (_burstTimer) clearInterval(_burstTimer);
  burst(card, _PAL_KEYS[tier]);                          // immediate burst
  _burstTimer = setInterval(() => burst(card, _PAL_KEYS[tier]), 700);
}

function stopBurst() {
  if (_burstTimer) { clearInterval(_burstTimer); _burstTimer = null; }
}

// ── Dialogue ──
let typer = null;

function typeText(text) {
  const el = document.getElementById('dlg');
  if (typer) clearTimeout(typer);
  el.innerHTML = '';
  let i = 0;
  function tick() {
    if (i < text.length) {
      el.innerHTML = text.slice(0, ++i) + '<span class="cursor"></span>';
      typer = setTimeout(tick, 55);
    } else {
      el.innerHTML = text + '<span class="cursor"></span>';
    }
  }
  tick();
}

// ── Live feed ──
const feedBody = document.getElementById('live-feed-body');
let _lastEventId = 0;

// Source label → display name
const SOURCE_LABELS = {
  TWITTER:  'Twitter',
  FOURMEME: '4meme',
  DEX:      'DexScr',
  GECKO:    'Gecko',
  ALCHEMY:  'Chain',
  SYSTEM:   'System',
};

function _appendEvent(evt, instant = false) {
  const el = document.createElement('div');
  el.className = 'chat-msg';
  if (instant) el.style.opacity = '1';
  const label = SOURCE_LABELS[evt.source] || evt.source;
  const msg   = (evt.message || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  el.innerHTML =
    `<span class="chat-user" style="color:${evt.color}">[${label}]</span>` +
    `<span class="chat-text"> ${msg}</span>`;
  feedBody.appendChild(el);
  // Keep max 6 rows visible
  while (feedBody.children.length > 6) feedBody.removeChild(feedBody.firstChild);
}

async function _pollFeed() {
  try {
    const res = await fetch(`/api/feed?since_id=${_lastEventId}&limit=10`);
    if (res.ok) {
      const events = await res.json();
      events.forEach(evt => {
        _appendEvent(evt);
        if (evt.id > _lastEventId) _lastEventId = evt.id;
      });
    }
  } catch { /* silently ignore network errors */ }
  setTimeout(_pollFeed, 5000);   // poll every 5 s
}

async function loadFeed() {
  // Load the latest 6 events on startup (instant, no animation)
  try {
    const res = await fetch('/api/feed?limit=6');
    if (res.ok) {
      const events = await res.json();
      events.forEach(evt => {
        _appendEvent(evt, true);
        if (evt.id > _lastEventId) _lastEventId = evt.id;
      });
    }
  } catch { /* fallback: empty feed is fine */ }

  // Start live polling
  setTimeout(_pollFeed, 5000);
}

// ── Particles ──
const PALETTES = {
  gray: ['#aaa','#ccc','#888','#ddd'],
  blue: ['#4da6ff','#7bbfff','#1a6bb5','#a0d4ff'],
  gold: ['#9b5cf6','#c084fc','#7c3aed','#e9d5ff','#a855f7'],
};
const SYMS = ['✦','★','✧','◆','·','✶'];

function burst(card, tier) {
  const pal = PALETTES[tier];
  const count = tier === 'gold' ? 10 : 5;
  const rect = card.getBoundingClientRect();
  for (let k = 0; k < count; k++) {
    setTimeout(() => {
      const p = document.createElement('div');
      p.className = 'fp';
      p.textContent = SYMS[Math.floor(Math.random() * SYMS.length)];
      p.style.color = pal[Math.floor(Math.random() * pal.length)];
      p.style.left  = (rect.left + Math.random() * rect.width) + 'px';
      p.style.top   = (rect.top  + Math.random() * rect.height * .5 + window.scrollY) + 'px';
      p.style.setProperty('--dx', ((Math.random() - .5) * 90) + 'px');
      p.style.setProperty('--dy', -(Math.random() * 70 + 20) + 'px');
      document.body.appendChild(p);
      setTimeout(() => p.remove(), 1000);
    }, k * 70);
  }
}

// ── History ──
const TIER_NAMES = ['Basic Pack', 'Elite Chest', 'Mythic Crate'];

async function openHistory() {
  if (!walletAddress) {
    showWarningToast('Wallet Not Connected', 'Please connect your wallet first!');
    return;
  }

  const modal    = document.getElementById('history-modal');
  const list     = document.getElementById('history-list');
  const subtitle = document.getElementById('history-subtitle');

  subtitle.textContent = shortAddr(walletAddress);
  list.innerHTML = '<div class="history-empty">Loading...</div>';
  modal.style.display = 'flex';

  try {
    const res = await fetch(`/api/purchases?wallet=${walletAddress}`);
    if (!res.ok) throw new Error();
    const records = await res.json();

    if (!records.length) {
      list.innerHTML = '<div class="history-empty">No purchases yet, boss!</div>';
      return;
    }

    list.innerHTML = '';
    records.forEach(r => {
      const date  = new Date(r.created_at).toLocaleDateString();
      const short = r.tx_hash.slice(0, 6) + '...' + r.tx_hash.slice(-4);

      // Build token chips
      const tokens = r.tokens || [];
      const tokenHtml = tokens.length
        ? tokens.map(t => {
            const logo = t.img_url
              ? `<img src="${t.img_url}" alt="${t.symbol}" class="htok-logo"
                      onerror="this.outerHTML='<span class=\\'htok-logo htok-logo-fb\\'>🪙</span>'">`
              : `<span class="htok-logo htok-logo-fb">🪙</span>`;
            const amt = t.success && t.amount
              ? `<span class="htok-amount">+${t.amount}</span>`
              : `<span class="htok-amount htok-fail">✗</span>`;
            return `<div class="htok ${t.success ? '' : 'htok-failed'}">
              ${logo}
              <span class="htok-sym">$${t.symbol}</span>
              ${amt}
            </div>`;
          }).join('')
        : '<span class="history-empty-inline">—</span>';

      const row = document.createElement('div');
      row.className = `history-row tier-${r.tier}`;
      row.innerHTML = `
        <div class="history-meta">
          <div class="history-tier">${TIER_NAMES[r.tier]}</div>
          <div class="history-date">${date}</div>
          <div class="history-price">${r.price_u} USDT</div>
          <a class="history-tx" href="https://bscscan.com/tx/${r.tx_hash}" target="_blank">${short} ↗</a>
        </div>
        <div class="history-tokens">${tokenHtml}</div>`;
      list.appendChild(row);
    });
  } catch {
    list.innerHTML = '<div class="history-empty">Failed to load. Is the server running?</div>';
  }
}

function closeHistoryModal(e) {
  if (e.target === document.getElementById('history-modal'))
    document.getElementById('history-modal').style.display = 'none';
}

// ── Init ──
window.addEventListener('load', async () => {
  // Show static welcome immediately
  setTimeout(() => typeText(LINES[0]), 600);

  // Silently pre-warm AI cache for first interactions
  ['welcome', 'tier_0', 'tier_1', 'tier_2'].forEach(ctx => fetchDialogue(ctx));

  // Fetch interval from .env via backend, then start auto-tick
  try {
    const res = await fetch('/api/ai/config');
    const { sophia_interval } = res.ok ? await res.json() : { sophia_interval: 30 };
    _startSophiaTimer(sophia_interval);
  } catch {
    _startSophiaTimer(30); // fallback if backend unreachable
  }

  loadFeed();
  initWalletListeners();
});
