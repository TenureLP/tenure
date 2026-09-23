// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @dev The handful of Foundry cheatcodes the suite needs, so the project has no external dependency.
interface Vm {
    function prank(address msgSender) external;
    function startPrank(address msgSender) external;
    function stopPrank() external;
    function warp(uint256 newTimestamp) external;
    function deal(address account, uint256 newBalance) external;
    function expectRevert(bytes4 revertData) external;
    function expectRevert() external;
    function label(address account, string calldata newLabel) external;
    function envOr(string calldata name, uint256 defaultValue) external view returns (uint256);
    function chainId(uint256 newChainId) external;
}

abstract contract MiniTest {
    Vm internal constant vm = Vm(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
    bool public IS_TEST = true;

    error AssertEqUint(uint256 left, uint256 right);
    error AssertEqAddress(address left, address right);
    error AssertGe(uint256 left, uint256 right);
    error AssertGt(uint256 left, uint256 right);
    error AssertLe(uint256 left, uint256 right);
    error AssertTrue(string reason);
    error AssertEqString(string left, string right);

    function makeAddr(string memory name) internal returns (address a) {
        a = address(uint160(uint256(keccak256(bytes(name)))));
        vm.label(a, name);
    }

    function assertEq(uint256 left, uint256 right) internal pure {
        if (left != right) revert AssertEqUint(left, right);
    }

    function assertEq(address left, address right) internal pure {
        if (left != right) revert AssertEqAddress(left, right);
    }

    /// @dev Compared by hash because Solidity will not compare two strings directly, and the
    ///      values that reach here are short labels rather than anything worth a byte loop.
    function assertEq(string memory left, string memory right) internal pure {
        if (keccak256(bytes(left)) != keccak256(bytes(right))) revert AssertEqString(left, right);
    }

    function assertGe(uint256 left, uint256 right) internal pure {
        if (left < right) revert AssertGe(left, right);
    }

    function assertGt(uint256 left, uint256 right) internal pure {
        if (left <= right) revert AssertGt(left, right);
    }

    function assertLe(uint256 left, uint256 right) internal pure {
        if (left > right) revert AssertLe(left, right);
    }

    /// @param reason Carried into the revert, so a loop over cases says which one failed.
    function assertTrue(bool condition, string memory reason) internal pure {
        if (!condition) revert AssertTrue(reason);
    }

    /// @dev Folds a fuzzed word into a range without throwing away draws, which `vm.assume` does.
    ///      Lived in Invariants.t.sol until a second suite needed it.
    function _bound(uint256 x, uint256 lo, uint256 hi) internal pure returns (uint256) {
        return hi <= lo ? lo : lo + (x % (hi - lo + 1));
    }
}
