// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {PoolKey} from "../libraries/Types.sol";

/// @notice Minimal surface of the Uniswap v4 PositionManager used by the vault.
interface IPositionManager {
    function modifyLiquidities(bytes calldata unlockData, uint256 deadline) external payable;
    function getPositionLiquidity(uint256 tokenId) external view returns (uint128 liquidity);
    function getPoolAndPositionInfo(uint256 tokenId) external view returns (PoolKey memory, uint256 info);

    // ERC-721
    function ownerOf(uint256 tokenId) external view returns (address);
    function transferFrom(address from, address to, uint256 tokenId) external;
    function approve(address spender, uint256 tokenId) external;
}
