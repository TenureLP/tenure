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

contract LeaseVaultTest is MiniTest {
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

    PoolKey key;
    bytes32 poolId;
    uint256 tokenId;

    uint128 constant PRICE = 1_000_000_000; // 1,000 USDG (6 decimals)
    uint128 constant RENT = 7_000_000; // 7 USDG for the term, i.e. 1 USDG / day over 7 days
    uint128 constant BUYBACK = 1_000_000_000; // 1,000 USDG
    uint128 constant FEE = 2_000_000; // flat 2 USDG
    uint32 constant TERM = 7 days;
    uint32 constant GRACE = 48 hours;

    function setUp() public {
        usdg = new MockERC20("Global Dollar", "USDG", 6);
        stock = new MockPausableERC20("NVDA Stock Token", "NVDAx");
        posm = new MockPositionManager();
        stateView = new MockStateView();
        registry = new AssetRegistry(address(this), feeRecipient, 5_000_000);
        vault = new LeaseVault(
            IERC20(address(usdg)),
            IPositionManager(address(posm)),
            IStateView(address(stateView)),
            registry
        );

        // currency0 < currency1 as in v4
        (address c0, address c1) = address(stock) < address(usdg)
            ? (address(stock), address(usdg))
            : (address(usdg), address(stock));
        key = PoolKey(Currency.wrap(c0), Currency.wrap(c1), 3000, 60, address(0));
        poolId = PoolId.unwrap(key.toId());

        registry.setPool(poolId, true, 1, 1_000, keccak256("screening-v1"));
        registry.setTerm(TERM, true);
        registry.setListingFee(FEE);
        stateView.setTick(poolId, 0);

        tokenId = posm.mint(seller, key, -600, 600, 10_000);

        usdg.mint(financier, 10_000_000_000);
        usdg.mint(financier2, 10_000_000_000);
        usdg.mint(seller, 10_000_000_000);
        vm.prank(financier);
        usdg.approve(address(vault), type(uint256).max);
        vm.prank(financier2);
        usdg.approve(address(vault), type(uint256).max);
        vm.prank(seller);
        usdg.approve(address(vault), type(uint256).max);
        vm.prank(seller);
        posm.approve(address(vault), tokenId);
    }

    // ------------------------------------------------------------------ helpers

    function _list() internal returns (uint256 id) {
        vm.prank(seller);
        id = vault.list(tokenId, PRICE, RENT, BUYBACK, TERM, 1 days);
    }

    function _listAndFund() internal returns (uint256 id) {
        id = _list();
        vm.prank(financier);
        vault.fund(id);
    }

    // ------------------------------------------------------------------ listing

    function test_list_transfersNftAndSnapshotsTerms() public {
        uint256 id = _list();
        assertEq(posm.ownerOf(tokenId), address(vault));
        LeaseVault.Deal memory d = vault.deal(id);
        assertEq(uint256(d.state), uint256(LeaseVault.State.Listed));
        assertEq(uint256(d.listingFee), uint256(FEE));
        assertEq(uint256(d.grace), uint256(GRACE));
        assertEq(d.seller, seller);
    }

    function test_list_rejectsPoolNotAllowed() public {
        registry.setPool(poolId, false, 0, 0, bytes32(0));
        vm.prank(seller);
        vm.expectRevert(LeaseVault.PoolNotAllowed.selector);
        vault.list(tokenId, PRICE, RENT, BUYBACK, TERM, 1 days);
    }

    function test_list_rejectsOutOfRange() public {
        stateView.setTick(poolId, 600);
        vm.prank(seller);
        vm.expectRevert(LeaseVault.OutOfRange.selector);
        vault.list(tokenId, PRICE, RENT, BUYBACK, TERM, 1 days);
    }

    function test_list_rejectsSubscriber() public {
        posm.setSubscribed(tokenId, true);
        vm.prank(seller);
        vm.expectRevert(LeaseVault.HasSubscriber.selector);
        vault.list(tokenId, PRICE, RENT, BUYBACK, TERM, 1 days);
    }

    function test_list_rejectsLowLiquidity() public {
        posm.setLiquidity(tokenId, 10);
        vm.prank(seller);
        vm.expectRevert(LeaseVault.LiquidityTooLow.selector);
        vault.list(tokenId, PRICE, RENT, BUYBACK, TERM, 1 days);
    }

    function test_list_rejectsRentPlusFeeAtOrAbovePrice() public {
        vm.prank(seller);
        vm.expectRevert(LeaseVault.BadEconomics.selector);
        vault.list(tokenId, 9_000_000, RENT, BUYBACK, TERM, 1 days);
    }

    function test_list_rejectsUnallowedTerm() public {
        vm.prank(seller);
        vm.expectRevert(LeaseVault.TermNotAllowed.selector);
        vault.list(tokenId, PRICE, RENT, BUYBACK, 3 days, 1 days);
    }

    function test_cancel_returnsNft() public {
        uint256 id = _list();
        vm.prank(seller);
        vault.cancel(id);
        vm.prank(seller);
        vault.withdrawPosition(tokenId);
        assertEq(posm.ownerOf(tokenId), seller);
    }

    // ------------------------------------------------------------------ funding

    function test_fund_paysSellerNetOfRentAndFlatFee() public {
        uint256 id = _listAndFund();
        assertEq(vault.balances(seller), PRICE - RENT - FEE);
        assertEq(vault.balances(feeRecipient), FEE);
        assertEq(usdg.balanceOf(address(vault)), PRICE);
        LeaseVault.Deal memory d = vault.deal(id);
        assertEq(d.financier, financier);
        assertEq(uint256(d.state), uint256(LeaseVault.State.Active));

        vm.prank(seller);
        vault.withdrawUSDG();
        assertEq(usdg.balanceOf(seller), 10_000_000_000 + PRICE - RENT - FEE);
    }

    function test_fund_rejectsSelfDeal() public {
        uint256 id = _list();
        vm.prank(seller);
        vm.expectRevert(LeaseVault.SelfDeal.selector);
        vault.fund(id);
    }

    function test_fund_rejectsExpiredListing() public {
        uint256 id = _list();
        vm.warp(block.timestamp + 1 days + 1);
        vm.prank(financier);
        vm.expectRevert(LeaseVault.ListingExpired.selector);
        vault.fund(id);
    }

    // ------------------------------------------------------------------ usufruct

    function test_collectFees_goesToLesseeDuringLease() public {
        uint256 id = _listAndFund();
        usdg.mint(address(posm), 3_000_000);
        stock.mint(address(posm), 1e18);
        if (Currency.unwrap(key.currency0) == address(stock)) {
            posm.setFees(tokenId, 1e18, 3_000_000);
        } else {
            posm.setFees(tokenId, 3_000_000, 1e18);
        }

        vm.warp(block.timestamp + 3 days);
        vm.prank(seller);
        vault.collectFees(id);
        assertEq(usdg.balanceOf(seller), 10_000_000_000 + 3_000_000);
        assertEq(stock.balanceOf(seller), 1e18);
    }

    function test_collectFees_onlyLessee() public {
        uint256 id = _listAndFund();
        vm.prank(financier);
        vm.expectRevert(LeaseVault.NotSeller.selector);
        vault.collectFees(id);
    }

    function test_collectFees_blockedAfterLeaseEnd() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + TERM + 1);
        vm.prank(seller);
        vm.expectRevert(LeaseVault.LeaseEnded.selector);
        vault.collectFees(id);
    }

    // ------------------------------------------------------------------ rent

    function test_rent_streamsLinearly() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + 3 days);
        assertEq(uint256(vault.accruedRent(id)),3_000_000);
        vault.claimRent(id);
        assertEq(vault.balances(financier), 3_000_000);
        vm.warp(block.timestamp + 10 days);
        assertEq(uint256(vault.accruedRent(id)),RENT); // capped at term
    }

    function test_rent_pausesWhileUnderlyingFrozen() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + 1 days);
        stock.setPaused(true);
        vault.checkpointFreeze(id);
        vm.warp(block.timestamp + 2 days);
        stock.setPaused(false);
        vault.checkpointFreeze(id);
        vm.warp(block.timestamp + 4 days); // day 7: 5 usable days
        assertEq(uint256(vault.accruedRent(id)),5_000_000);

        // Frozen time is refunded to the lessee at settlement.
        vm.warp(block.timestamp + GRACE);
        vm.prank(financier);
        vault.release(id);
        assertEq(vault.balances(financier), 5_000_000);
        assertEq(vault.balances(seller), PRICE - RENT - FEE + 2_000_000);
    }

    function test_rent_frozenAcrossLeaseEndIsBounded() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + 6 days);
        stock.setPaused(true);
        vault.checkpointFreeze(id);
        vm.warp(block.timestamp + 5 days); // well past the term
        stock.setPaused(false);
        vault.checkpointFreeze(id);
        assertEq(uint256(vault.accruedRent(id)),6_000_000);
    }

    // ------------------------------------------------------------------ buyback

    function test_buyBack_atTerm_paysFinancierPriceAndFullRent() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + TERM);
        vm.prank(seller);
        vault.buyBack(id);

        assertEq(vault.balances(financier), uint256(BUYBACK) + RENT);
        assertEq(vault.balances(seller), PRICE - RENT - FEE); // no refund
        vm.prank(seller);
        vault.withdrawPosition(tokenId);
        assertEq(posm.ownerOf(tokenId), seller);
        assertEq(uint256(vault.deal(id).state), uint256(LeaseVault.State.BoughtBack));
    }

    function test_buyBack_early_refundsUnaccruedRent() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + 2 days);
        vm.prank(seller);
        vault.buyBack(id);
        assertEq(vault.balances(financier), uint256(BUYBACK) + 2_000_000);
        assertEq(vault.balances(seller), PRICE - RENT - FEE + 5_000_000);
    }

    function test_buyBack_duringGrace_stillAllowed() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + TERM + 1 hours);
        vm.prank(seller);
        vault.buyBack(id);
        assertEq(uint256(vault.deal(id).state), uint256(LeaseVault.State.BoughtBack));
    }

    function test_buyBack_afterRelease_impossible() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + TERM + GRACE);
        vm.prank(financier);
        vault.release(id);
        vm.prank(seller);
        vm.expectRevert(LeaseVault.NotActive.selector);
        vault.buyBack(id);
    }

    function test_buyBack_accountsForRentAlreadyClaimed() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + 3 days);
        vault.claimRent(id);
        vm.warp(block.timestamp + 4 days);
        vm.prank(seller);
        vault.buyBack(id);
        assertEq(vault.balances(financier), uint256(BUYBACK) + RENT);
    }

    // ------------------------------------------------------------------ release

    function test_release_beforeGraceEnd_reverts() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + TERM + GRACE - 1);
        vm.prank(financier);
        vm.expectRevert(LeaseVault.GraceNotOver.selector);
        vault.release(id);
    }

    function test_release_afterGrace_deliversPositionToFinancier() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + TERM + GRACE);
        vm.prank(financier);
        vault.release(id);
        assertEq(vault.balances(financier), RENT);
        vm.prank(financier);
        vault.withdrawPosition(tokenId);
        assertEq(posm.ownerOf(tokenId), financier);
        assertEq(uint256(vault.deal(id).state), uint256(LeaseVault.State.Released));
    }

    function test_release_onlyFinancier() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + TERM + GRACE);
        vm.prank(seller);
        vm.expectRevert(LeaseVault.NotFinancier.selector);
        vault.release(id);
    }

    // ------------------------------------------------------------------ ownership transfer

    function test_transferFinancierPosition_settlesRentAndMovesOwnership() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + 2 days);
        vm.prank(financier);
        vault.transferFinancierPosition(id, financier2);
        assertEq(vault.balances(financier), 2_000_000);
        assertEq(vault.deal(id).financier, financier2);

        vm.warp(block.timestamp + 5 days + GRACE);
        vm.prank(financier2);
        vault.release(id);
        assertEq(vault.balances(financier2), 5_000_000);
        vm.prank(financier2);
        vault.withdrawPosition(tokenId);
        assertEq(posm.ownerOf(tokenId), financier2);
    }

    function test_transferFinancierPosition_neverToLessee() public {
        uint256 id = _listAndFund();
        vm.prank(financier);
        vm.expectRevert(LeaseVault.SelfDeal.selector);
        vault.transferFinancierPosition(id, seller);
    }

    // ------------------------------------------------------------------ invariants

    function test_vaultUsdgNeverBelowLiabilities() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + 4 days);
        vault.claimRent(id);
        vm.prank(seller);
        vault.buyBack(id);
        uint256 liabilities = vault.balances(seller) + vault.balances(financier) + vault.balances(feeRecipient);
        assertEq(usdg.balanceOf(address(vault)), liabilities);
    }

    function test_registryChangesDoNotAffectActiveDeal() public {
        uint256 id = _listAndFund();
        registry.setListingFee(5_000_000);
        registry.setGrace(7 days);
        LeaseVault.Deal memory d = vault.deal(id);
        assertEq(uint256(d.listingFee), uint256(FEE));
        assertEq(uint256(d.grace), uint256(GRACE));
    }
}
