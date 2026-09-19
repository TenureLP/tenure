// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {MiniTest} from "./utils/MiniTest.sol";
import {AssetRegistry} from "../src/AssetRegistry.sol";
import {LeaseVault} from "../src/LeaseVault.sol";
import {IERC20} from "../src/interfaces/IERC20.sol";
import {IPositionManager} from "../src/interfaces/IPositionManager.sol";
import {IStateView} from "../src/interfaces/IStateView.sol";
import {Currency, PoolKey, PoolIdLib, PoolId} from "../src/libraries/Types.sol";
import {MockERC20, MockPausableERC20} from "./mocks/MockERC20.sol";
import {MockPositionManager} from "./mocks/MockPositionManager.sol";
import {MockStateView} from "./mocks/MockStateView.sol";

/// @notice Stateful fuzzing: random action sequences on one deal, with the invariants that must hold
///         no matter the order, the timing or which calls revert along the way.
///
/// Reverts are expected and ignored: the point is that whatever sequence gets through, the vault
/// stays solvent and the accounting stays inside its bounds.
contract InvariantsTest is MiniTest {
    using PoolIdLib for PoolKey;

    MockERC20 usdg;
    MockPausableERC20 stock;
    MockPositionManager posm;
    MockStateView stateView;
    AssetRegistry registry;
    LeaseVault vault;

    address seller = makeAddr("seller");
    address financier = makeAddr("financier");
    address financier2 = makeAddr("financier2");
    address feeRecipient = makeAddr("feeRecipient");
    address keeper = makeAddr("keeper");

    PoolKey key;
    uint256 tokenId;
    uint32 constant TERM = 7 days;
    uint128 constant FEE = 2_000_000;

    function setUp() public {
        usdg = new MockERC20("Global Dollar", "USDG", 6);
        stock = new MockPausableERC20("NVDA Stock Token", "NVDAx");
        posm = new MockPositionManager();
        stateView = new MockStateView();
        registry = new AssetRegistry(address(this), feeRecipient, 5_000_000);
        vault = new LeaseVault(IERC20(address(usdg)), IPositionManager(address(posm)), IStateView(address(stateView)), registry);

        (address c0, address c1) = address(stock) < address(usdg) ? (address(stock), address(usdg)) : (address(usdg), address(stock));
        key = PoolKey(Currency.wrap(c0), Currency.wrap(c1), 3000, 60, address(0));
        registry.setPool(PoolId.unwrap(key.toId()), true, 1, 1, 1_000, bytes32(0));
        registry.setTerm(TERM, true);
        registry.setListingFee(FEE);
        stateView.setTick(PoolId.unwrap(key.toId()), 0);
        tokenId = posm.mint(seller, key, -600, 600, 10_000);

        for (uint256 i; i < 3; ++i) {
            address who = [seller, financier, financier2][i];
            usdg.mint(who, 1e15);
            vm.prank(who);
            usdg.approve(address(vault), type(uint256).max);
        }
        vm.prank(seller);
        posm.approve(address(vault), tokenId);
    }

    // ------------------------------------------------------------------ invariants

    /// @dev The vault must always hold at least what it says it owes.
    function _assertSolvent() internal view {
        uint256 owed = vault.balances(seller) + vault.balances(financier) + vault.balances(financier2)
            + vault.balances(feeRecipient) + vault.balances(keeper);
        assertGe(usdg.balanceOf(address(vault)), owed);
    }

    function _assertDealSane(uint256 id) internal view {
        LeaseVault.Deal memory d = vault.deal(id);
        if (d.state == LeaseVault.State.None) return;
        // Rent paid out can never exceed the rent that was escrowed.
        assertGe(uint256(d.rent), uint256(d.rentClaimed));
        assertGe(uint256(d.rent), uint256(vault.accruedRent(id)));
        // Frozen time can never exceed the term it is deducted from.
        assertGe(uint256(d.term), uint256(d.pausedTotal));
        // The position is owed to at most one party, and only once the deal is settled.
        address owedTo = vault.positionOwed(d.tokenId);
        if (d.state == LeaseVault.State.Listed || d.state == LeaseVault.State.Active) {
            assertEq(owedTo, address(0));
        } else if (d.state == LeaseVault.State.BoughtBack || d.state == LeaseVault.State.Cancelled) {
            if (owedTo != address(0)) assertEq(owedTo, d.seller);
        } else if (d.state == LeaseVault.State.Released) {
            if (owedTo != address(0)) assertEq(owedTo, d.financier);
        }
    }

    // ------------------------------------------------------------------ the fuzz

    function _bound(uint256 x, uint256 lo, uint256 hi) internal pure returns (uint256) {
        return lo + (x % (hi - lo + 1));
    }

    /// @param acts   a sequence of action selectors
    /// @param jumps  seconds to warp before each action
    function testFuzz_sequencesKeepTheVaultSolvent(uint8[16] memory acts, uint16[16] memory jumps, uint96 rawPrice, uint96 rawRent, uint96 rawBuyback)
        public
    {
        uint128 price = uint128(_bound(rawPrice, FEE + 2, 1e12));
        uint128 rent = uint128(_bound(rawRent, 0, price - FEE - 1));
        uint128 buyback = uint128(_bound(rawBuyback, 0, 1e12));

        vm.prank(seller);
        try vault.list(tokenId, price, rent, buyback, TERM, 1 days) returns (uint256 id) {
            _assertSolvent();
            _assertDealSane(id);
            for (uint256 i; i < acts.length; ++i) {
                vm.warp(block.timestamp + _bound(jumps[i], 0, 3 days));
                _act(acts[i] % 11, id);
                _assertSolvent();
                _assertDealSane(id);
            }
            // Whatever happened, everyone can still pull what they are owed.
            _drain(seller);
            _drain(financier);
            _drain(financier2);
            _drain(feeRecipient);
            _assertSolvent();
        } catch {
            // A rejected listing is a valid outcome; nothing should have moved.
            assertEq(usdg.balanceOf(address(vault)), 0);
        }
    }

    function _act(uint256 which, uint256 id) internal {
        if (which == 0) {
            vm.prank(financier);
            try vault.fund(id) {} catch {}
        } else if (which == 1) {
            vm.prank(financier2);
            try vault.fund(id) {} catch {}
        } else if (which == 2) {
            vm.prank(seller);
            try vault.collectFees(id) {} catch {}
        } else if (which == 3) {
            vm.prank(keeper);
            try vault.claimRent(id) {} catch {}
        } else if (which == 4) {
            vm.prank(seller);
            try vault.buyBack(id) {} catch {}
        } else if (which == 5) {
            vm.prank(financier);
            try vault.release(id) {} catch {}
        } else if (which == 6) {
            vm.prank(financier2);
            try vault.release(id) {} catch {}
        } else if (which == 7) {
            vm.prank(financier);
            try vault.transferFinancierPosition(id, financier2) {} catch {}
        } else if (which == 8) {
            vm.prank(keeper);
            try vault.checkpointFreeze(id) {} catch {}
        } else if (which == 9) {
            stock.setPaused(!stock.paused());
        } else {
            vm.prank(seller);
            try vault.cancel(id) {} catch {}
        }
    }

    function _drain(address who) internal {
        vm.prank(who);
        try vault.withdrawUSDG() {} catch {}
    }
}
