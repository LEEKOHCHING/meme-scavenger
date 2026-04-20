// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function allowance(address owner, address spender) external view returns (uint256);
}

contract MemeScavenger {
    address public owner;
    IERC20 public immutable usdt;

    // BSC USDT has 18 decimals — 10/20/30 USDT
    uint256[3] public prices = [
        10 * 10 ** 18,
        20 * 10 ** 18,
        30 * 10 ** 18
    ];

    event Purchase(
        address indexed buyer,
        uint8  indexed tier,
        uint256 price,
        uint256 timestamp
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(address _usdt) {
        owner = msg.sender;
        usdt  = IERC20(_usdt);
    }

    function buy(uint8 tier) external {
        require(tier < 3, "Invalid tier");
        uint256 price = prices[tier];
        require(
            usdt.transferFrom(msg.sender, owner, price),  // 直接打入 owner 钱包
            "USDT transfer failed"
        );
        emit Purchase(msg.sender, tier, price, block.timestamp);
    }

    function setOwner(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Zero address");
        owner = newOwner;
    }

    function getPrice(uint8 tier) external view returns (uint256) {
        require(tier < 3, "Invalid tier");
        return prices[tier];
    }
}
