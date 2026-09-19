// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {MiniTest} from "./utils/MiniTest.sol";
import {TenureToken} from "../src/TenureToken.sol";

contract TenureTokenTest is MiniTest {
    TenureToken token;

    address holder = makeAddr("holder");
    address other = makeAddr("other");
    address spender = makeAddr("spender");

    uint256 constant SUPPLY = 1_000_000_000 ether;

    function setUp() public {
        token = new TenureToken(holder, SUPPLY);
    }

    // ------------------------------------------------------------------ what exists

    function test_mintsTheWholeSupplyOnce() public view {
        assertEq(token.totalSupply(), SUPPLY);
        assertEq(token.balanceOf(holder), SUPPLY);
    }

    function test_transferMovesBalance() public {
        vm.prank(holder);
        token.transfer(other, 100 ether);
        assertEq(token.balanceOf(other), 100 ether);
        assertEq(token.balanceOf(holder), SUPPLY - 100 ether);
    }

    function test_transferFromSpendsAllowance() public {
        vm.prank(holder);
        token.approve(spender, 100 ether);
        vm.prank(spender);
        token.transferFrom(holder, other, 40 ether);
        assertEq(token.allowance(holder, spender), 60 ether);
        assertEq(token.balanceOf(other), 40 ether);
    }

    /// Every wallet and router assumes this, and it saves a storage write per transfer.
    function test_maxAllowanceIsNotSpentDown() public {
        vm.prank(holder);
        token.approve(spender, type(uint256).max);
        vm.prank(spender);
        token.transferFrom(holder, other, 1 ether);
        assertEq(token.allowance(holder, spender), type(uint256).max);
    }

    // ------------------------------------------------------------------ what cannot happen

    function test_cannotSpendWhatYouDoNotHave() public {
        vm.prank(other);
        vm.expectRevert(TenureToken.InsufficientBalance.selector);
        token.transfer(holder, 1);
    }

    function test_cannotSpendBeyondTheAllowance() public {
        vm.prank(holder);
        token.approve(spender, 10 ether);
        vm.prank(spender);
        vm.expectRevert(TenureToken.InsufficientAllowance.selector);
        token.transferFrom(holder, other, 11 ether);
    }

    /// Burning is its own function, so a mistyped address reverts instead of quietly destroying
    /// somebody's balance.
    function test_transferToZeroReverts() public {
        vm.prank(holder);
        vm.expectRevert(TenureToken.ZeroAddress.selector);
        token.transfer(address(0), 1 ether);
    }

    function test_supplyCannotBeSentNowhereAtDeployment() public {
        vm.expectRevert(TenureToken.ZeroAddress.selector);
        new TenureToken(address(0), SUPPLY);
    }

    // ------------------------------------------------------------------ burning

    function test_burnReducesSupplyForever() public {
        vm.prank(holder);
        token.burn(1_000 ether);
        assertEq(token.totalSupply(), SUPPLY - 1_000 ether);
        assertEq(token.balanceOf(holder), SUPPLY - 1_000 ether);
    }

    /// A buyback contract can be given a budget to burn and nothing else.
    function test_burnFromSpendsAllowance() public {
        vm.prank(holder);
        token.approve(spender, 500 ether);
        vm.prank(spender);
        token.burnFrom(holder, 500 ether);
        assertEq(token.totalSupply(), SUPPLY - 500 ether);
        assertEq(token.allowance(holder, spender), 0);
    }

    function test_cannotBurnBeyondTheAllowance() public {
        vm.prank(holder);
        token.approve(spender, 1 ether);
        vm.prank(spender);
        vm.expectRevert(TenureToken.InsufficientAllowance.selector);
        token.burnFrom(holder, 2 ether);
    }

    // ------------------------------------------------------------------ what is absent

    /// The point of the contract. If any of these ever resolves, somebody added a power to a token
    /// that is supposed to have none, and this test is how that gets noticed.
    function test_noPrivilegedFunctionExists() public view {
        string[9] memory dangerous = [
            "owner()",
            "mint(address,uint256)",
            "pause()",
            "unpause()",
            "blacklist(address)",
            "setFee(uint256)",
            "upgradeTo(address)",
            "transferOwnership(address)",
            "renounceOwnership()"
        ];
        for (uint256 i; i < dangerous.length; ++i) {
            (bool ok,) = address(token).staticcall(abi.encodeWithSignature(dangerous[i]));
            assertTrue(!ok, dangerous[i]);
        }
    }

    /// Total supply only ever falls, whatever sequence of transfers and burns happens.
    function testFuzz_supplyNeverGrows(uint96 send, uint96 burnA, uint96 burnB) public {
        uint256 before = token.totalSupply();

        uint256 moved = _bound(send, 0, SUPPLY);
        vm.prank(holder);
        token.transfer(other, moved);

        // Read the balances out of the way. A balanceOf() evaluated inside the call arguments is
        // the next call after the prank, and swallows it, so the burn would run as the test
        // contract instead of the holder.
        uint256 otherBurn = _bound(burnA, 0, token.balanceOf(other));
        uint256 holderBurn = _bound(burnB, 0, token.balanceOf(holder));

        vm.prank(other);
        token.burn(otherBurn);
        vm.prank(holder);
        token.burn(holderBurn);

        assertLe(token.totalSupply(), before);
        assertEq(token.totalSupply(), token.balanceOf(holder) + token.balanceOf(other));
    }
}
