// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {MiniTest} from "./utils/MiniTest.sol";
import {LeaseVault} from "../src/LeaseVault.sol";
import {IERC20} from "../src/interfaces/IERC20.sol";
import {IPositionManager} from "../src/interfaces/IPositionManager.sol";
import {IStateView} from "../src/interfaces/IStateView.sol";
import {Currency, PoolKey, PoolIdLib, PoolId} from "../src/libraries/Types.sol";
import {MockERC20, MockPausableERC20, MockReturnBombERC20, MockSilentERC20} from "./mocks/MockERC20.sol";
import {MockPositionManager} from "./mocks/MockPositionManager.sol";
import {MockStateView} from "./mocks/MockStateView.sol";

contract LeaseVaultTest is MiniTest {
    using PoolIdLib for PoolKey;

    MockERC20 usdg;
    MockPausableERC20 stock;
    MockPositionManager posm;
    MockStateView stateView;
    LeaseVault vault;

    address seller = makeAddr("seller");
    address financier = makeAddr("financier");
    address financier2 = makeAddr("financier2");
    address sellerBuilder = makeAddr("sellerBuilder");
    address financierBuilder = makeAddr("financierBuilder");

    PoolKey key;
    bytes32 poolId;
    uint256 tokenId;

    uint128 constant PRICE = 1_000_000_000; // 1,000 USDG (6 decimals)
    uint128 constant RENT = 7_000_000; // 7 USDG for the term, i.e. 1 USDG / day over 7 days
    uint128 constant BUYBACK = 1_000_000_000; // 1,000 USDG
    uint32 constant TERM = 7 days;
    uint32 constant GRACE = 48 hours;

    function setUp() public {
        usdg = new MockERC20("Global Dollar", "USDG", 6);
        stock = new MockPausableERC20("NVDA Stock Token", "NVDAx");
        posm = new MockPositionManager();
        stateView = new MockStateView();
        vault = new LeaseVault(
            IERC20(address(usdg)), IPositionManager(address(posm)), IStateView(address(stateView))
        );

        // currency0 < currency1 as in v4
        (address c0, address c1) = address(stock) < address(usdg)
            ? (address(stock), address(usdg))
            : (address(usdg), address(stock));
        key = PoolKey(Currency.wrap(c0), Currency.wrap(c1), 3000, 60, address(0));
        poolId = PoolId.unwrap(key.toId());

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

    /// The offer every test starts from. Terms belong to the deal now, so a test that cares about
    /// one of them copies this and changes it, instead of reaching for a global setting.
    function _terms() internal pure returns (LeaseVault.Terms memory) {
        return LeaseVault.Terms({
            price: PRICE,
            rent: RENT,
            buybackPrice: BUYBACK,
            term: TERM,
            grace: GRACE,
            listingDuration: 1 days,
            maxFrozenBps: 2_500,
            freezeProbe: 1,
            builder: address(0),
            builderFee: 0
        });
    }

    function _list() internal returns (uint256 id) {
        vm.prank(seller);
        id = vault.list(tokenId, _terms());
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
        assertEq(uint256(d.grace), uint256(GRACE));
        assertEq(uint256(d.maxFrozenBps), 2_500);
        assertEq(uint256(d.freezeProbe), 1);
        assertEq(d.seller, seller);
    }

    /// Nothing anywhere decides which pools deserve to be dealt in. Whoever is parting with money
    /// decides that, one layer up, and can change their mind without asking this contract.
    function test_list_needsNobodysPermission() public {
        MockERC20 anything = new MockERC20("Whatever", "WHT", 18);
        (address c0, address c1) = address(anything) < address(usdg)
            ? (address(anything), address(usdg))
            : (address(usdg), address(anything));
        PoolKey memory k = PoolKey(Currency.wrap(c0), Currency.wrap(c1), 3000, 60, address(0));
        stateView.setTick(PoolId.unwrap(k.toId()), 0);
        uint256 tid = posm.mint(seller, k, -600, 600, 10_000);
        vm.prank(seller);
        posm.approve(address(vault), tid);

        vm.prank(seller);
        uint256 id = vault.list(tid, _terms());
        assertEq(uint256(vault.deal(id).state), uint256(LeaseVault.State.Listed));
    }

    function test_list_rejectsOutOfRange() public {
        stateView.setTick(poolId, 600);
        vm.prank(seller);
        vm.expectRevert(LeaseVault.OutOfRange.selector);
        vault.list(tokenId, _terms());
    }

    function test_list_rejectsSubscriber() public {
        posm.setSubscribed(tokenId, true);
        vm.prank(seller);
        vm.expectRevert(LeaseVault.HasSubscriber.selector);
        vault.list(tokenId, _terms());
    }

    /// An empty position has no usufruct to lease, which is the substance of the whole deal. How
    /// much liquidity is worth financing is a different question, and not one for this contract.
    function test_list_rejectsEmptyPosition() public {
        posm.setLiquidity(tokenId, 0);
        vm.prank(seller);
        vm.expectRevert(LeaseVault.NoLiquidity.selector);
        vault.list(tokenId, _terms());
    }

    function test_list_rejectsRentAtOrAbovePrice() public {
        LeaseVault.Terms memory t = _terms();
        t.price = RENT;
        vm.prank(seller);
        vm.expectRevert(LeaseVault.BadEconomics.selector);
        vault.list(tokenId, t);
    }

    /// The financier is paid for the use of the asset, not for the passage of time. A buyback above
    /// the sale price is a guaranteed spread on top of the rent, which is a financing cost wearing
    /// the clothes of a sale. There is no owner here to forbid it later, so the code does.
    function test_list_rejectsBuybackAboveSale() public {
        LeaseVault.Terms memory t = _terms();
        t.buybackPrice = PRICE + 1;
        vm.prank(seller);
        vm.expectRevert(LeaseVault.BuybackAboveSale.selector);
        vault.list(tokenId, t);
    }

    function test_list_allowsBuybackBelowSale() public {
        // Only the financier is worse off, and only by their own choice to fund it.
        LeaseVault.Terms memory t = _terms();
        t.buybackPrice = PRICE - 1;
        vm.prank(seller);
        uint256 id = vault.list(tokenId, t);
        assertEq(uint256(vault.deal(id).buybackPrice), uint256(PRICE - 1));
    }

    /// The bounds are constants. Nobody can be talked into widening them, and a financier who has
    /// read this file once knows the worst offer they can ever be shown.
    function test_list_rejectsTermsOutsideTheConstantBounds() public {
        LeaseVault.Terms memory t = _terms();

        t.term = vault.MAX_TERM() + 1;
        vm.prank(seller);
        vm.expectRevert(LeaseVault.BadTerm.selector);
        vault.list(tokenId, t);

        t = _terms();
        t.grace = vault.MIN_GRACE() - 1;
        vm.prank(seller);
        vm.expectRevert(LeaseVault.BadGrace.selector);
        vault.list(tokenId, t);

        // A high figure suits the seller, who picks it, so the ceiling is what protects the other side.
        t = _terms();
        t.maxFrozenBps = vault.MAX_FROZEN_BPS() + 1;
        vm.prank(seller);
        vm.expectRevert(LeaseVault.BadFrozenCap.selector);
        vault.list(tokenId, t);

        t = _terms();
        t.freezeProbe = 2;
        vm.prank(seller);
        vm.expectRevert(LeaseVault.BadProbe.selector);
        vault.list(tokenId, t);
    }

    /// A term this contract used to refuse because an owner had not enabled it.
    function test_list_acceptsAnyTermInsideTheBounds() public {
        LeaseVault.Terms memory t = _terms();
        t.term = 3 days;
        vm.prank(seller);
        uint256 id = vault.list(tokenId, t);
        assertEq(uint256(vault.deal(id).term), 3 days);
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

    function test_fund_paysSellerNetOfRentAndNothingElse() public {
        uint256 id = _listAndFund();
        // No protocol fee exists. Nothing is taken between the financier and the seller.
        assertEq(vault.balances(seller), PRICE - RENT);
        assertEq(usdg.balanceOf(address(vault)), PRICE);
        LeaseVault.Deal memory d = vault.deal(id);
        assertEq(d.financier, financier);
        assertEq(uint256(d.state), uint256(LeaseVault.State.Active));

        vm.prank(seller);
        vault.withdrawUSDG();
        assertEq(usdg.balanceOf(seller), 10_000_000_000 + PRICE - RENT);
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
        // A freeze only counts while somebody keeps observing it, so a keeper checks in every 6 h.
        for (uint256 i; i < 8; ++i) {
            vm.warp(block.timestamp + 6 hours);
            vault.checkpointFreeze(id);
        }
        stock.setPaused(false);
        vault.checkpointFreeze(id);
        vm.warp(block.timestamp + 4 days);
        // The halt really lasted 2 days, but a deal may only credit 25% of its term as frozen, so
        // 42 h of it counts and the lessee pays for the remaining 6. That ceiling is the price of
        // making the sampling unexploitable; a pool whose tokens halt for longer needs it raised.
        uint256 capped = uint256(TERM) * 2_500 / 10_000;
        uint256 expected = uint256(RENT) * (TERM - capped) / TERM;
        assertEq(uint256(vault.accruedRent(id)), expected);

        // Frozen time is refunded to the lessee at settlement.
        vm.warp(block.timestamp + GRACE);
        vm.prank(financier);
        vault.release(id);
        assertEq(vault.balances(financier), expected);
        assertEq(vault.balances(seller), PRICE - RENT + (RENT - expected));
    }

    /// Repeated checkpoints during brief halts cannot wipe out the rent: sampling cannot tell a
    /// week-long freeze from twenty-eight one-second ones, so the total is capped for the deal.
    function test_rent_repeatedBriefHaltsCannotWipeOutTheRent() public {
        uint256 id = _listAndFund();
        for (uint256 i; i < 28; ++i) {
            vm.warp(block.timestamp + 6 hours);
            stock.setPaused(true);
            vault.checkpointFreeze(id); // frozen for exactly this instant
            stock.setPaused(false);
        }
        vm.warp(block.timestamp + TERM);
        // 25% of the term is the ceiling these terms set, so three quarters of the rent survives.
        assertEq(uint256(vault.accruedRent(id)), RENT - RENT / 4);
    }

    /// A token that answers the probe with nothing at all has no freeze switch, and must not be
    /// read as permanently frozen: nobody could ever undo that.
    function test_rent_silentTokenIsNotTreatedAsFrozen() public {
        MockSilentERC20 silent = new MockSilentERC20();
        (address c0, address c1) =
            address(silent) < address(usdg) ? (address(silent), address(usdg)) : (address(usdg), address(silent));
        PoolKey memory k = PoolKey(Currency.wrap(c0), Currency.wrap(c1), 3000, 60, address(0));
        bytes32 pid = PoolId.unwrap(k.toId());
        stateView.setTick(pid, 0);
        uint256 tid = posm.mint(seller, k, -600, 600, 10_000);
        vm.prank(seller);
        posm.approve(address(vault), tid);
        vm.prank(seller);
        uint256 id = vault.list(tid, _terms());
        vm.prank(financier);
        vault.fund(id);
        vm.warp(block.timestamp + TERM);
        vault.checkpointFreeze(id);
        assertEq(uint256(vault.accruedRent(id)), RENT); // full rent, nothing was ever frozen
    }

    /// An unobserved freeze cannot run forever: whoever opens it must keep proving it is still there.
    /// Without this, one call during a one-second halt would stop the rent for the rest of the term.
    function test_rent_unobservedFreezeStopsCountingAfterMaxGap() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + 1 days);
        stock.setPaused(true);
        vault.checkpointFreeze(id); // opened, and never looked at again
        stock.setPaused(false); // the halt lasted an instant
        vm.warp(block.timestamp + 6 days);

        // Only the 6 hours after the sighting are credited, not the six days.
        uint256 gap = vault.MAX_FREEZE_GAP();
        assertEq(uint256(vault.accruedRent(id)), RENT - uint128(uint256(RENT) * gap / TERM));
        vault.checkpointFreeze(id); // closing it later cannot recover the lost time either
        assertEq(uint256(vault.deal(id).pausedTotal), gap);
    }

    /// A token that answers the freeze probe with megabytes must not be able to brick a deal.
    function test_rent_returnBombCannotBrickTheDeal() public {
        MockReturnBombERC20 bomb = new MockReturnBombERC20();
        (address c0, address c1) =
            address(bomb) < address(usdg) ? (address(bomb), address(usdg)) : (address(usdg), address(bomb));
        PoolKey memory bombKey = PoolKey(Currency.wrap(c0), Currency.wrap(c1), 3000, 60, address(0));
        bytes32 bombPool = PoolId.unwrap(bombKey.toId());
        stateView.setTick(bombPool, 0);
        uint256 bombToken = posm.mint(seller, bombKey, -600, 600, 10_000);
        vm.prank(seller);
        posm.approve(address(vault), bombToken);

        vm.prank(seller);
        uint256 id = vault.list(bombToken, _terms());
        vm.prank(financier);
        vault.fund(id);

        // Every entry point still fits in a normal gas budget. The probe itself is starved by its
        // own stipend and reports nothing, which costs the financier nothing and the lessee nothing:
        // what matters is that the deal can still be settled and the position still comes out.
        vm.warp(block.timestamp + 1 days);
        vault.checkpointFreeze{gas: 400_000}(id);
        vm.prank(seller);
        vault.collectFees{gas: 400_000}(id);
        vault.claimRent{gas: 400_000}(id);

        vm.warp(block.timestamp + TERM + GRACE);
        vm.prank(financier);
        vault.release{gas: 400_000}(id);
        vm.prank(financier);
        vault.withdrawPosition(bombToken);
        assertEq(posm.ownerOf(bombToken), financier);
    }

    function test_rent_frozenAcrossLeaseEndIsBounded() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + 6 days);
        stock.setPaused(true);
        vault.checkpointFreeze(id);
        vm.warp(block.timestamp + 5 days); // well past the term
        stock.setPaused(false);
        vault.checkpointFreeze(id);
        // The freeze started on day 6 and is capped at 6 h, so 6 days and 18 hours are billable.
        assertEq(uint256(vault.accruedRent(id)), RENT - uint128(uint256(RENT) * 6 hours / TERM));
    }

    // ------------------------------------------------------------------ buyback

    function test_buyBack_atTerm_paysFinancierPriceAndFullRent() public {
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + TERM);
        vm.prank(seller);
        vault.buyBack(id);

        assertEq(vault.balances(financier), uint256(BUYBACK) + RENT);
        assertEq(vault.balances(seller), PRICE - RENT); // no refund
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
        assertEq(vault.balances(seller), PRICE - RENT + 5_000_000);
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
        uint256 liabilities = vault.balances(seller) + vault.balances(financier);
        assertEq(usdg.balanceOf(address(vault)), liabilities);
    }

    // ------------------------------------------------------------------ builder codes

    /// Each side pays whoever brought them, out of their own money, and the vault keeps none of it.
    function test_fund_paysEachSideOwnBuilder() public {
        uint128 sellerFee = PRICE / 200; // half the cap
        uint128 financierFee = PRICE / 400;

        LeaseVault.Terms memory t = _terms();
        t.builder = sellerBuilder;
        t.builderFee = sellerFee;
        vm.prank(seller);
        uint256 id = vault.list(tokenId, t);

        uint256 financierBefore = usdg.balanceOf(financier);
        vm.prank(financier);
        vault.fund(id, financierBuilder, financierFee);

        // The seller pays their own, out of the proceeds they agreed to.
        assertEq(vault.balances(seller), PRICE - RENT - sellerFee);
        assertEq(vault.balances(sellerBuilder), sellerFee);
        // The financier pays theirs on top, so it never touches what the seller was promised.
        assertEq(vault.balances(financierBuilder), financierFee);
        assertEq(financierBefore - usdg.balanceOf(financier), uint256(PRICE) + financierFee);

        // Nothing stayed behind: what came in is exactly what is owed out.
        assertEq(
            usdg.balanceOf(address(vault)),
            vault.balances(seller) + vault.balances(sellerBuilder) + vault.balances(financierBuilder) + RENT
        );
    }

    function test_fund_withNoBuilderCostsNothingExtra() public {
        uint256 before = usdg.balanceOf(financier);
        _listAndFund();
        assertEq(before - usdg.balanceOf(financier), PRICE);
        assertEq(vault.balances(seller), PRICE - RENT);
    }

    /// Naming a fee and no recipient would burn it.
    function test_list_rejectsAFeeWithNoBuilder() public {
        LeaseVault.Terms memory t = _terms();
        t.builderFee = 1;
        vm.prank(seller);
        vm.expectRevert(LeaseVault.BadBuilderFee.selector);
        vault.list(tokenId, t);
    }

    /// The party paying rarely builds the transaction they sign. The cap bounds what a front end
    /// filling the field in for them can help itself to.
    function test_builderFeeIsCappedOnBothSides() public {
        // Read out of the way: evaluating it inside the call arguments would be the next call
        // after expectRevert, and would swallow the expectation.
        uint128 tooMuch = PRICE / uint128(vault.MAX_BUILDER_FEE_DIVISOR()) + 1;

        LeaseVault.Terms memory t = _terms();
        t.builder = sellerBuilder;
        t.builderFee = tooMuch;
        vm.prank(seller);
        vm.expectRevert(LeaseVault.BadBuilderFee.selector);
        vault.list(tokenId, t);

        uint256 id = _list();
        vm.prank(financier);
        vm.expectRevert(LeaseVault.BadBuilderFee.selector);
        vault.fund(id, financierBuilder, tooMuch);
    }

    /// A builder fee that ate the whole price would leave the seller selling for nothing.
    function test_list_rejectsABuilderFeeThatLeavesTheSellerNothing() public {
        LeaseVault.Terms memory t = _terms();
        t.price = RENT + 2;
        t.buybackPrice = RENT + 2;
        t.builder = sellerBuilder;
        t.builderFee = 2;
        vm.prank(seller);
        vm.expectRevert(LeaseVault.BadEconomics.selector);
        vault.list(tokenId, t);
    }

    /// Deals do not share settings, so there is no state anyone could change to reach into one
    /// that is already running. This is what replaced reading a mutable registry at funding time.
    function test_dealsDoNotShareTerms() public {
        uint256 first = _listAndFund();

        uint256 second = posm.mint(seller, key, -600, 600, 10_000);
        vm.prank(seller);
        posm.approve(address(vault), second);
        LeaseVault.Terms memory t = _terms();
        t.grace = 7 days;
        t.maxFrozenBps = 0;
        vm.prank(seller);
        uint256 other = vault.list(second, t);

        assertEq(uint256(vault.deal(first).grace), uint256(GRACE));
        assertEq(uint256(vault.deal(first).maxFrozenBps), 2_500);
        assertEq(uint256(vault.deal(other).grace), 7 days);
        assertEq(uint256(vault.deal(other).maxFrozenBps), 0);
    }
}
