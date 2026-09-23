// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {MiniTest} from "../utils/MiniTest.sol";
import {LeaseVault} from "../../src/LeaseVault.sol";
import {IERC20} from "../../src/interfaces/IERC20.sol";
import {IPositionManager} from "../../src/interfaces/IPositionManager.sol";
import {IStateView} from "../../src/interfaces/IStateView.sol";
import {PoolKey, PoolIdLib, PoolId, PositionInfoLib} from "../../src/libraries/Types.sol";
import {TestToken} from "../../src/testnet/TestToken.sol";
import {
    TestPositionFaucet,
    IPoolManagerLite,
    IPositionManagerLite,
    IPermit2Lite
} from "../../src/testnet/TestPositionFaucet.sol";
import {OpeningPrice} from "../../script/DeployFaucet.s.sol";

interface IMintable {
    function mint(address to, uint256 value) external;
}

/// @notice The faucet against the real Uniswap v4 deployment and the real LeaseVault on Robinhood
///         Chain testnet.
/// @dev Run with:  forge test --match-path "test/fork/FaucetFork*" --fork-url https://rpc.testnet.chain.robinhood.com -vv
///      Every test is a no-op unless the chain id is 46630, so the offline suite stays green.
contract FaucetForkTest is MiniTest {
    using PoolIdLib for PoolKey;
    using PositionInfoLib for uint256;

    IPositionManager constant POSM = IPositionManager(0x58daec3116aae6D93017bAAea7749052E8a04fA7);
    IStateView constant STATE_VIEW = IStateView(0xF3334192D15450CdD385c8B70e03f9A6bD9E673b);
    address constant POOL_MANAGER = 0x8366a39CC670B4001A1121B8F6A443A643e40951;
    address constant PERMIT2 = 0x000000000022D473030F116dDEE9F6B43aC78BA3;
    address constant TUSDG = 0x182794FbDc0Db20341cd61D4D856b0D5101221A4;
    LeaseVault constant VAULT = LeaseVault(0x27797A2c3428a92C498eD01f3B1c77f636990F7C);

    TestToken teth;
    TestPositionFaucet faucet;
    address lessee = makeAddr("lessee");
    address financier = makeAddr("financier");
    address passerby = makeAddr("passerby");
    bool live;

    function setUp() public {
        live = block.chainid == 46630;
        if (!live) return;
        teth = new TestToken("Test Ether (worthless)", "tETH", 18);
        faucet = new TestPositionFaucet(
            IPoolManagerLite(POOL_MANAGER),
            IPositionManagerLite(address(POSM)),
            STATE_VIEW,
            IPermit2Lite(PERMIT2),
            address(teth),
            TUSDG,
            OpeningPrice.sqrtPriceX96(address(teth), TUSDG)
        );
    }

    function _tick() internal view returns (int24 tick) {
        (, tick,,) = STATE_VIEW.getSlot0(PoolId.unwrap(faucet.poolKey().toId()));
    }

    function _balance(address token, address who) internal view returns (uint256) {
        return IERC20(token).balanceOf(who);
    }

    /// The whole point: one call, and the caller holds a position the vault will take.
    function test_give_handsTheCallerAnInRangePosition() public {
        if (!live) return;
        vm.prank(lessee);
        uint256 id = faucet.give();

        assertEq(POSM.ownerOf(id), lessee);
        assertEq(uint256(POSM.getPositionLiquidity(id)), uint256(faucet.LIQUIDITY()));
        (PoolKey memory key, uint256 info) = POSM.getPoolAndPositionInfo(id);
        assertEq(uint256(PoolId.unwrap(key.toId())), uint256(PoolId.unwrap(faucet.poolKey().toId())));
        int24 tick = _tick();
        assertTrue(info.tickLower() <= tick && tick < info.tickUpper(), "the price must sit inside the range");
        assertTrue(!info.hasSubscriber(), "a subscriber would make the vault refuse it");
    }

    /// The round trips must not walk the price out of everybody's range.
    function test_manyCalls_leaveThePriceWhereItStarted() public {
        if (!live) return;
        vm.prank(lessee);
        faucet.give();
        int24 start = _tick();
        for (uint256 i; i < 12; ++i) {
            vm.prank(passerby);
            faucet.give();
        }
        int24 drift = _tick() - start;
        if (drift < 0) drift = -drift;
        assertLe(uint256(uint24(drift)), uint256(uint24(faucet.HALF_WIDTH() / 4)));
    }

    /// A whole deal on the vault that is actually deployed: list, fund, earn fees from other
    /// people's calls, collect them, buy back, take the position home.
    function test_aWholeDeal_onTheDeployedVault() public {
        if (!live) return;
        vm.prank(lessee);
        uint256 id = faucet.give();

        LeaseVault.Terms memory t = LeaseVault.Terms({
            price: 1_000e6,
            rent: 10e6,
            buybackPrice: 1_000e6,
            term: 1 days,
            grace: 1 days,
            listingDuration: 1 days,
            maxFrozenBps: 0,
            freezeProbe: 0,
            builder: address(0),
            builderFee: 0
        });
        vm.startPrank(lessee);
        POSM.approve(address(VAULT), id);
        uint256 dealId = VAULT.list(id, t);
        vm.stopPrank();
        assertEq(POSM.ownerOf(id), address(VAULT));

        IMintable(TUSDG).mint(financier, 1_000e6);
        vm.startPrank(financier);
        IERC20(TUSDG).approve(address(VAULT), 1_000e6);
        VAULT.fund(dealId);
        vm.stopPrank();

        // Somebody else asking for a position trades through the pool, both ways.
        vm.prank(passerby);
        faucet.give();
        vm.prank(passerby);
        faucet.give();

        (address t0, address t1) = (faucet.token0(), faucet.token1());
        uint256 before0 = _balance(t0, lessee);
        uint256 before1 = _balance(t1, lessee);
        vm.prank(lessee);
        VAULT.collectFees(dealId);
        assertTrue(
            _balance(t0, lessee) > before0 || _balance(t1, lessee) > before1, "the lessee must collect real fees"
        );

        IMintable(TUSDG).mint(lessee, 1_000e6);
        vm.startPrank(lessee);
        IERC20(TUSDG).approve(address(VAULT), 1_000e6);
        VAULT.buyBack(dealId);
        VAULT.withdrawPosition(id);
        vm.stopPrank();
        assertEq(POSM.ownerOf(id), lessee);
    }

    function test_onlyThePoolManager_canCallBack() public {
        if (!live) return;
        vm.expectRevert(TestPositionFaucet.NotPoolManager.selector);
        faucet.unlockCallback(abi.encode(true));
    }
}
