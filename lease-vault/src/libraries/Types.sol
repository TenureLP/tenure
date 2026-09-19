// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @dev Mirror of Uniswap v4 core types, kept minimal so the vault has no external dependency.
type Currency is address;
type PoolId is bytes32;

struct PoolKey {
    Currency currency0;
    Currency currency1;
    uint24 fee;
    int24 tickSpacing;
    address hooks;
}

library PoolIdLib {
    /// @dev Identical to v4-core PoolIdLibrary.toId: keccak256 of the 160-byte encoded key.
    function toId(PoolKey memory key) internal pure returns (PoolId) {
        return PoolId.wrap(keccak256(abi.encode(key)));
    }
}

/// @dev Decoder for the packed PositionInfo of the v4 PositionManager:
///      200 bits poolId | 24 bits tickUpper | 24 bits tickLower | 8 bits hasSubscriber
library PositionInfoLib {
    function hasSubscriber(uint256 info) internal pure returns (bool) {
        return info & 0xFF != 0;
    }

    function tickLower(uint256 info) internal pure returns (int24) {
        return int24(uint24((info >> 8) & 0xFFFFFF));
    }

    function tickUpper(uint256 info) internal pure returns (int24) {
        return int24(uint24((info >> 32) & 0xFFFFFF));
    }
}

/// @dev Only the two PositionManager actions the vault ever issues.
library Actions {
    uint8 internal constant DECREASE_LIQUIDITY = 0x01;
    uint8 internal constant TAKE_PAIR = 0x11;
}
