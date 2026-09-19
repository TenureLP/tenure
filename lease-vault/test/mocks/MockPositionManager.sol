// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Currency, PoolKey} from "../../src/libraries/Types.sol";
import {IERC20} from "../../src/interfaces/IERC20.sol";

/// @dev Minimal stand-in for the Uniswap v4 PositionManager: ERC-721 ownership, packed
///      PositionInfo, and a `modifyLiquidities` that only understands the fee-collection pair
///      (DECREASE_LIQUIDITY with zero liquidity followed by TAKE_PAIR).
contract MockPositionManager {
    struct Pos {
        PoolKey key;
        int24 tickLower;
        int24 tickUpper;
        uint128 liquidity;
        bool subscribed;
        uint256 fees0;
        uint256 fees1;
    }

    mapping(uint256 => Pos) internal _pos;
    mapping(uint256 => address) public ownerOf;
    mapping(uint256 => address) public getApproved;
    mapping(address => mapping(address => bool)) public isApprovedForAll;
    uint256 public nextTokenId = 1;

    function mint(address to, PoolKey memory key, int24 tl, int24 tu, uint128 liq) external returns (uint256 id) {
        id = nextTokenId++;
        _pos[id] = Pos(key, tl, tu, liq, false, 0, 0);
        ownerOf[id] = to;
    }

    /// @dev Fees to be paid out on the next collect; the mock must hold the tokens.
    function setFees(uint256 id, uint256 f0, uint256 f1) external {
        _pos[id].fees0 = f0;
        _pos[id].fees1 = f1;
    }

    function setSubscribed(uint256 id, bool s) external {
        _pos[id].subscribed = s;
    }

    function setLiquidity(uint256 id, uint128 liq) external {
        _pos[id].liquidity = liq;
    }

    // ---- ERC-721 subset ----
    function approve(address spender, uint256 id) external {
        require(msg.sender == ownerOf[id], "not owner");
        getApproved[id] = spender;
    }

    function setApprovalForAll(address op, bool ok) external {
        isApprovedForAll[msg.sender][op] = ok;
    }

    function transferFrom(address from, address to, uint256 id) external {
        require(ownerOf[id] == from, "wrong from");
        require(_isApprovedOrOwner(msg.sender, id), "not approved");
        ownerOf[id] = to;
        delete getApproved[id];
        _pos[id].subscribed = false; // v4 unsubscribes on transfer
    }

    function _isApprovedOrOwner(address who, uint256 id) internal view returns (bool) {
        address o = ownerOf[id];
        return who == o || getApproved[id] == who || isApprovedForAll[o][who];
    }

    // ---- v4 views ----
    function getPositionLiquidity(uint256 id) external view returns (uint128) {
        return _pos[id].liquidity;
    }

    function getPoolAndPositionInfo(uint256 id) external view returns (PoolKey memory, uint256 info) {
        Pos storage p = _pos[id];
        info = (uint256(uint24(p.tickUpper)) << 32) | (uint256(uint24(p.tickLower)) << 8) | (p.subscribed ? 1 : 0);
        return (p.key, info);
    }

    // ---- v4 actions ----
    function modifyLiquidities(bytes calldata unlockData, uint256) external payable {
        (bytes memory actions, bytes[] memory params) = abi.decode(unlockData, (bytes, bytes[]));
        require(actions.length == 2, "mock: two actions");
        require(uint8(actions[0]) == 0x01 && uint8(actions[1]) == 0x11, "mock: unsupported");
        (uint256 id, uint256 liq,,,) = abi.decode(params[0], (uint256, uint256, uint128, uint128, bytes));
        require(_isApprovedOrOwner(msg.sender, id), "NotApproved");
        require(liq == 0, "mock: only fee collection");
        (Currency c0, Currency c1, address recipient) = abi.decode(params[1], (Currency, Currency, address));
        Pos storage p = _pos[id];
        require(Currency.unwrap(c0) == Currency.unwrap(p.key.currency0), "c0");
        require(Currency.unwrap(c1) == Currency.unwrap(p.key.currency1), "c1");
        uint256 f0 = p.fees0;
        uint256 f1 = p.fees1;
        p.fees0 = 0;
        p.fees1 = 0;
        if (f0 != 0) IERC20(Currency.unwrap(c0)).transfer(recipient, f0);
        if (f1 != 0) IERC20(Currency.unwrap(c1)).transfer(recipient, f1);
    }
}
