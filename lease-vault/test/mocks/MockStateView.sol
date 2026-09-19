// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

contract MockStateView {
    mapping(bytes32 => int24) public tickOf;

    function setTick(bytes32 poolId, int24 tick) external {
        tickOf[poolId] = tick;
    }

    function getSlot0(bytes32 poolId) external view returns (uint160, int24, uint24, uint24) {
        return (0, tickOf[poolId], 0, 0);
    }
}
