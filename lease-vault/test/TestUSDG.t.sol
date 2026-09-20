// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {MiniTest} from "./utils/MiniTest.sol";
import {TestUSDG} from "../src/TestUSDG.sol";

/// @dev A test token still settles every figure on a test network, so it is held to the parts of
///      the ERC-20 contract the vault actually relies on: six decimals, an allowance that is spent
///      rather than ignored, and a transfer that cannot overdraw.
contract TestUSDGTest is MiniTest {
    TestUSDG token;

    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    address spender = makeAddr("spender");

    function setUp() public {
        token = new TestUSDG();
    }

    /// The whole reason this contract exists is to stand in for a six-decimal token. At eighteen,
    /// every amount on the test network is a trillion times off and every figure still looks
    /// plausible, which is the worst kind of wrong.
    function test_hasSixDecimalsLikeTheTokenItStandsIn() public view {
        assertEq(token.decimals(), 6);
    }

    /// Named so nobody mistakes it for the real one, in the two places a wallet will show it.
    function test_saysWhatItIs() public view {
        assertEq(token.symbol(), "tUSDG");
        assertEq(token.name(), "Test USDG (worthless)");
    }

    function test_anyoneCanMintToAnyone() public {
        vm.prank(alice);
        token.mint(bob, 1_000_000);
        assertEq(token.balanceOf(bob), 1_000_000);
        assertEq(token.totalSupply(), 1_000_000);
    }

    function test_transferMovesBalance() public {
        token.mint(alice, 500);
        vm.prank(alice);
        token.transfer(bob, 200);
        assertEq(token.balanceOf(alice), 300);
        assertEq(token.balanceOf(bob), 200);
    }

    function test_cannotSendWhatYouDoNotHave() public {
        token.mint(alice, 10);
        vm.prank(alice);
        vm.expectRevert(TestUSDG.InsufficientBalance.selector);
        token.transfer(bob, 11);
    }

    function test_transferFromSpendsTheAllowance() public {
        token.mint(alice, 100);
        vm.prank(alice);
        token.approve(spender, 60);
        vm.prank(spender);
        token.transferFrom(alice, bob, 25);
        assertEq(token.allowance(alice, spender), 35);
        assertEq(token.balanceOf(bob), 25);
    }

    function test_transferFromRefusesBeyondTheAllowance() public {
        token.mint(alice, 100);
        vm.prank(alice);
        token.approve(spender, 10);
        vm.prank(spender);
        vm.expectRevert(TestUSDG.InsufficientAllowance.selector);
        token.transferFrom(alice, bob, 11);
    }

    /// The vault approves exact amounts, but plenty of tooling approves the maximum, and a token
    /// that decrements from it would eventually disagree with itself.
    function test_infiniteAllowanceIsNotDecremented() public {
        token.mint(alice, 100);
        vm.prank(alice);
        token.approve(spender, type(uint256).max);
        vm.prank(spender);
        token.transferFrom(alice, bob, 40);
        assertEq(token.allowance(alice, spender), type(uint256).max);
    }

    function test_refusesTheZeroAddress() public {
        vm.expectRevert(TestUSDG.ZeroAddress.selector);
        token.mint(address(0), 1);

        token.mint(alice, 1);
        vm.prank(alice);
        vm.expectRevert(TestUSDG.ZeroAddress.selector);
        token.transfer(address(0), 1);
    }
}
