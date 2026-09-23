// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {MiniTest} from "./utils/MiniTest.sol";
import {TestToken} from "../src/testnet/TestToken.sol";
import {
    TestPositionFaucet,
    IPoolManagerLite,
    IPositionManagerLite,
    IPermit2Lite
} from "../src/testnet/TestPositionFaucet.sol";
import {IStateView} from "../src/interfaces/IStateView.sol";
import {OpeningPrice} from "../script/DeployFaucet.s.sol";

/// @dev What can be checked without a Uniswap deployment: the second test token, the faucet's
///      refusals, and the opening price. The faucet's real work is checked on a fork of the testnet,
///      in test/fork/FaucetFork.t.sol.
contract TestPositionFaucetTest is MiniTest {
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");

    function test_testToken_takesItsNameAndDecimalsFromItsDeployer() public {
        TestToken t = new TestToken("Test Ether (worthless)", "tETH", 18);
        assertEq(t.name(), "Test Ether (worthless)");
        assertEq(t.symbol(), "tETH");
        assertEq(uint256(t.decimals()), 18);
    }

    function test_testToken_anyoneCanMint_andTransfersCannotOverdraw() public {
        TestToken t = new TestToken("T", "T", 18);
        vm.prank(alice);
        t.mint(bob, 5);
        assertEq(t.balanceOf(bob), 5);
        vm.prank(bob);
        vm.expectRevert(TestToken.InsufficientBalance.selector);
        t.transfer(alice, 6);
    }

    /// A faucet of worthless positions beside real ones is how somebody lists the wrong thing, so
    /// the constructor refuses mainnet before it touches anything.
    function test_faucet_refusesMainnet() public {
        vm.chainId(4663);
        vm.expectRevert(TestPositionFaucet.NotOnMainnet.selector);
        new TestPositionFaucet(
            IPoolManagerLite(address(1)), IPositionManagerLite(address(2)), IStateView(address(3)),
            IPermit2Lite(address(4)), address(5), address(6), 1 << 96
        );
    }

    function test_faucet_refusesAPoolOfOneToken() public {
        vm.chainId(46630);
        vm.expectRevert(TestPositionFaucet.SameToken.selector);
        new TestPositionFaucet(
            IPoolManagerLite(address(1)), IPositionManagerLite(address(2)), IStateView(address(3)),
            IPermit2Lite(address(4)), address(5), address(5), 1 << 96
        );
    }

    /// 3,000 tUSDG per tETH, whichever way the two addresses sort. Squared back, the fixed-point
    /// price must land on 3e9 / 1e18 raw units, or on its inverse.
    function test_openingPrice_isThreeThousandEitherWayRound() public pure {
        address low = address(0x1000);
        address high = address(0x2000);

        uint256 s = OpeningPrice.sqrtPriceX96(low, high); // tETH is token0
        uint256 raw = s * s / 2 ** 96; // price × 2^96
        uint256 expected = uint256(3000e6) * 2 ** 96 / 1e18;
        assertLe(_diff(raw, expected) * 1e6, expected); // within a millionth

        s = OpeningPrice.sqrtPriceX96(high, low); // tUSDG is token0
        raw = s * s / 2 ** 96;
        expected = uint256(1e18) * 2 ** 96 / 3000e6;
        assertLe(_diff(raw, expected) * 1e6, expected);
    }

    function _diff(uint256 a, uint256 b) private pure returns (uint256) {
        return a > b ? a - b : b - a;
    }
}
