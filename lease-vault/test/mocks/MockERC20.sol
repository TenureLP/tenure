// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

contract MockERC20 {
    string public name;
    string public symbol;
    uint8 public immutable decimals;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    constructor(string memory name_, string memory symbol_, uint8 decimals_) {
        name = name_;
        symbol = symbol_;
        decimals = decimals_;
    }

    function mint(address to, uint256 amount) external {
        totalSupply += amount;
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _move(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 a = allowance[from][msg.sender];
        require(a >= amount, "allowance");
        if (a != type(uint256).max) allowance[from][msg.sender] = a - amount;
        _move(from, to, amount);
        return true;
    }

    function _move(address from, address to, uint256 amount) internal virtual {
        require(balanceOf[from] >= amount, "balance");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
    }
}

/// @dev Mimics a regulated stock token with a global pause switch.
contract MockPausableERC20 is MockERC20 {
    bool public paused;

    constructor(string memory n, string memory s) MockERC20(n, s, 18) {}

    function setPaused(bool p) external {
        paused = p;
    }

    function _move(address from, address to, uint256 amount) internal override {
        require(!paused, "paused");
        super._move(from, to, amount);
    }
}

/// @dev A token whose `paused()` answers with an enormous blob. Before the vault bounded its probe,
///      copying that blob cost quadratic memory and pushed every entry point of a deal over the
///      block gas limit, stranding the position forever.
contract MockReturnBombERC20 is MockERC20 {
    uint256 public words = 100_000;

    constructor() MockERC20("Bomb", "BOMB", 18) {}

    function setWords(uint256 n) external {
        words = n;
    }

    fallback() external {
        // paused()
        if (msg.sig == 0x5c975abb) {
            uint256 n = words;
            assembly {
                let size := mul(n, 0x20)
                let ptr := mload(0x40)
                mstore(add(ptr, size), 0)
                return(ptr, size)
            }
        }
    }
}

/// @dev Answers every unknown selector successfully with no return data, the way a token with a
///      permissive fallback does. That is indistinguishable from "no such function" and must not be
///      read as frozen.
contract MockSilentERC20 is MockERC20 {
    constructor() MockERC20("Silent", "SIL", 18) {}

    fallback() external {}
}
