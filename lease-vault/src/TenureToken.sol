// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @title TenureToken
/// @notice A fixed-supply ERC-20. Everything that could be used against a holder was left out.
///
/// @dev **This is not the token that was launched.** TEN, at
///      0x4bA94fB1D3fDF414afdc955CD29836016eDF3531 on Robinhood Chain, was created by the Pons
///      launchpad from its own template, not from this file. That contract was checked against the
///      same list of privileged selectors this one is tested against and answers none of them; see
///      docs/TOKEN.md for what was verified and how to repeat it.
///
///      This file stays because the test beside it is the definition of what a token here is
///      allowed to be, and because anything deployed later should have to pass it.
///
/// @dev There is no owner, no minter, no pause, no blacklist, no fee on transfer, no upgrade path
///      and no hook that a later contract could be pointed at. The whole supply exists after the
///      constructor and can only ever go down, because holders may burn their own balance.
///
///      That is the entire contract, and it is deliberate. A token is the one place in a system
///      where a hidden power is worth the most to whoever holds it and costs the most to everyone
///      else, so the safest design is the one with nothing to hold.
///
///      What this contract does **not** do is give the token a purpose. It has none on its own: no
///      revenue reaches it, no vote is counted with it, and nothing here promises either. Anything
///      of that kind has to be built, verifiably, in contracts beside this one, and claimed only
///      once it is running. See docs/TOKEN.md, which says the same thing at greater length.
contract TenureToken {
    string public constant name = "Tenure";
    string public constant symbol = "TENURE";
    uint8 public constant decimals = 18;

    /// @notice Minted once, in the constructor, and never again. There is no mint function.
    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    error ZeroAddress();
    error InsufficientBalance();
    error InsufficientAllowance();

    /// @param recipient Receives the entire supply. Where it goes from there is a disclosure, not a
    ///                  contract: see docs/TOKEN.md.
    /// @param supply    Total units, including decimals.
    constructor(address recipient, uint256 supply) {
        if (recipient == address(0)) revert ZeroAddress();
        totalSupply = supply;
        balanceOf[recipient] = supply;
        emit Transfer(address(0), recipient, supply);
    }

    function transfer(address to, uint256 value) external returns (bool) {
        _transfer(msg.sender, to, value);
        return true;
    }

    function approve(address spender, uint256 value) external returns (bool) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        // The max allowance is treated as infinite, which is what every wallet and router expects,
        // and it saves a storage write on every transfer.
        if (allowed != type(uint256).max) {
            if (allowed < value) revert InsufficientAllowance();
            unchecked {
                allowance[from][msg.sender] = allowed - value;
            }
        }
        _transfer(from, to, value);
        return true;
    }

    /// @notice Destroy your own tokens. Supply falls and never comes back.
    function burn(uint256 value) external {
        _burn(msg.sender, value);
    }

    /// @notice Destroy tokens you have been given an allowance over.
    /// @dev Present so that a contract can be given a budget to burn, which is how a buyback ends
    ///      without that contract ever being able to touch anything else.
    function burnFrom(address from, uint256 value) external {
        uint256 allowed = allowance[from][msg.sender];
        if (allowed != type(uint256).max) {
            if (allowed < value) revert InsufficientAllowance();
            unchecked {
                allowance[from][msg.sender] = allowed - value;
            }
        }
        _burn(from, value);
    }

    function _transfer(address from, address to, uint256 value) private {
        // Sending to the zero address is how tokens are burned by accident. Burning is a separate
        // function on purpose, so a mistyped transfer reverts instead of destroying somebody's
        // balance silently.
        if (to == address(0)) revert ZeroAddress();
        uint256 held = balanceOf[from];
        if (held < value) revert InsufficientBalance();
        unchecked {
            balanceOf[from] = held - value;
            balanceOf[to] += value; // cannot overflow: the sum of all balances is totalSupply
        }
        emit Transfer(from, to, value);
    }

    function _burn(address from, uint256 value) private {
        uint256 held = balanceOf[from];
        if (held < value) revert InsufficientBalance();
        unchecked {
            balanceOf[from] = held - value;
            totalSupply -= value;
        }
        emit Transfer(from, address(0), value);
    }
}
