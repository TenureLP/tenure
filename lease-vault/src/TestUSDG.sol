// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @title TestUSDG
/// @notice A settlement token for test networks, and for nothing else.
///
/// @dev Robinhood Chain's testnet carries the whole Uniswap v4 deployment at the same addresses as
///      its mainnet, but it has no USDG. `LeaseVault` settles in one ERC-20 chosen at construction,
///      so testing the vault anywhere but mainnet needs a stand-in. This is that stand-in.
///
///      **Anyone can mint it, without limit.** That is the point: a tester needs money and there is
///      no faucet for a token that does not exist. It also means this contract is worthless by
///      construction, which is the only honest thing a test token can be, and it is why the name
///      says so rather than trying to pass for the real one.
///
///      Deploying this on a chain where real money moves would be a deliberate act, so the deploy
///      script refuses to do it on chain 4663 rather than trusting anybody to remember.
contract TestUSDG {
    string public constant name = "Test USDG (worthless)";
    string public constant symbol = "tUSDG";
    /// @notice Six, like the token it stands in for. Getting this wrong makes every figure a
    ///         trillion times off, which is exactly the bug a test network exists to find early.
    uint8 public constant decimals = 6;

    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    error ZeroAddress();
    error InsufficientBalance();
    error InsufficientAllowance();

    /// @notice Mint to anyone, any amount, from any address. See the note above.
    function mint(address to, uint256 value) external {
        if (to == address(0)) revert ZeroAddress();
        totalSupply += value;
        balanceOf[to] += value;
        emit Transfer(address(0), to, value);
    }

    function transfer(address to, uint256 value) external returns (bool) {
        _transfer(msg.sender, to, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        if (allowed != type(uint256).max) {
            if (allowed < value) revert InsufficientAllowance();
            allowance[from][msg.sender] = allowed - value;
        }
        _transfer(from, to, value);
        return true;
    }

    function approve(address spender, uint256 value) external returns (bool) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function _transfer(address from, address to, uint256 value) private {
        if (to == address(0)) revert ZeroAddress();
        uint256 balance = balanceOf[from];
        if (balance < value) revert InsufficientBalance();
        unchecked {
            balanceOf[from] = balance - value;
            balanceOf[to] += value;
        }
        emit Transfer(from, to, value);
    }
}
