// ── Contract addresses ──
const CONTRACT_ADDRESS = '0x3c878b4aC226410F507951BBF648bA1307dA67fc'; // MemeScavenger on BSC Mainnet
const USDT_ADDRESS     = '0x55d398326f99059fF775485246999027B3197955'; // BSC Mainnet USDT
const WBNB_ADDRESS     = '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c'; // Wrapped BNB
const PANCAKE_ROUTER   = '0x10ED43C718714eb63d5aA57B78B54704E256024E'; // PancakeSwap V2 Router

// ── ABIs ──
const MEME_ABI = [
  'function buy(uint8 tier) external',
  'function prices(uint256) external view returns (uint256)',
  'function getPrice(uint8 tier) external view returns (uint256)',
  'event Purchase(address indexed buyer, uint8 indexed tier, uint256 price, uint256 timestamp)',
];

const USDT_ABI = [
  'function approve(address spender, uint256 amount) external returns (bool)',
  'function allowance(address owner, address spender) external view returns (uint256)',
  'function balanceOf(address account) external view returns (uint256)',
];

const ROUTER_ABI = [
  'function swapExactTokensForTokensSupportingFeeOnTransferTokens(uint256 amountIn, uint256 amountOutMin, address[] calldata path, address to, uint256 deadline) external',
  'function getAmountsOut(uint256 amountIn, address[] calldata path) external view returns (uint256[] memory amounts)',
];

const ERC20_BALANCE_ABI = [
  'function balanceOf(address account) external view returns (uint256)',
  'function decimals() external view returns (uint8)',
  'function symbol() external view returns (string)',
];

// ── Demo mode flag ──
const DEMO_MODE = true;
