// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {MiniTest} from "../utils/MiniTest.sol";
import {AssetRegistry} from "../../src/AssetRegistry.sol";
import {LeaseVault} from "../../src/LeaseVault.sol";
import {IERC20} from "../../src/interfaces/IERC20.sol";
import {IPositionManager} from "../../src/interfaces/IPositionManager.sol";
import {IStateView} from "../../src/interfaces/IStateView.sol";
import {Currency, PoolKey, PoolIdLib, PoolId, Actions} from "../../src/libraries/Types.sol";

/// @notice Integration test against the real Uniswap v4 deployment on Robinhood Chain.
/// @dev Run with:  forge test --match-path "test/fork/*" --fork-url https://rpc.mainnet.chain.robinhood.com -vv
///      Every test is a no-op unless the chain id is 4663, so the offline suite stays green.
///      FORK_TOKEN_ID selects the live position to use; its current owner is impersonated.
contract VaultForkTest is MiniTest {
    using PoolIdLib for PoolKey;

    IERC20 constant USDG = IERC20(0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168);
    IPositionManager constant POSM = IPositionManager(0x58daec3116aae6D93017bAAea7749052E8a04fA7);
    IStateView constant STATE_VIEW = IStateView(0xF3334192D15450CdD385c8B70e03f9A6bD9E673b);
    address constant POOL_MANAGER = 0x8366a39CC670B4001A1121B8F6A443A643e40951; // holds every pool's USDG

    uint128 constant PRICE = 1_000_000_000; // 1,000 USDG
    uint128 constant RENT = 7_000_000; // 7 USDG over 7 days
    uint128 constant BUYBACK = 1_000_000_000;
    uint32 constant TERM = 7 days;

    AssetRegistry registry;
    LeaseVault vault;
    address financier = makeAddr("financier");
    address seller;
    uint256 tokenId;
    PoolKey key;
    bool live;

    function setUp() public {
        live = block.chainid == 4663;
        if (!live) return;

        tokenId = vm.envOr("FORK_TOKEN_ID", uint256(2908278));
        seller = POSM.ownerOf(tokenId);
        (key,) = POSM.getPoolAndPositionInfo(tokenId);

        registry = new AssetRegistry(address(this), address(0xFEE), 5_000_000);
        vault = new LeaseVault(USDG, POSM, STATE_VIEW, registry);
        registry.setPool(PoolId.unwrap(key.toId()), true, 2, 1, 1, bytes32(0));
        registry.setTerm(TERM, true);

        // Fund both parties with real USDG taken from the PoolManager's balance (fork only).
        vm.startPrank(POOL_MANAGER);
        USDG.transfer(financier, 5_000_000_000);
        USDG.transfer(seller, 5_000_000_000);
        vm.stopPrank();
        vm.deal(seller, 1 ether);

        vm.prank(financier);
        USDG.approve(address(vault), type(uint256).max);
        vm.startPrank(seller);
        USDG.approve(address(vault), type(uint256).max);
        POSM.approve(address(vault), tokenId);
        vm.stopPrank();
    }

    function _bal(Currency c, address who) internal view returns (uint256) {
        address t = Currency.unwrap(c);
        return t == address(0) ? who.balance : IERC20(t).balanceOf(who);
    }

    function _listAndFund() internal returns (uint256 id) {
        vm.prank(seller);
        id = vault.list(tokenId, PRICE, RENT, BUYBACK, TERM, 1 days);
        vm.prank(financier);
        vault.fund(id);
    }

    function test_fork_list_custodiesTheRealNft() public {
        if (!live) return;
        vm.prank(seller);
        uint256 id = vault.list(tokenId, PRICE, RENT, BUYBACK, TERM, 1 days);
        assertEq(POSM.ownerOf(tokenId), address(vault));
        LeaseVault.Deal memory d = vault.deal(id);
        assertEq(uint256(d.poolId), uint256(PoolId.unwrap(key.toId())));
    }

    function test_fork_collectFees_paysLessee_andNeverTouchesLiquidity() public {
        if (!live) return;
        uint256 id = _listAndFund();
        uint128 liqBefore = POSM.getPositionLiquidity(tokenId);
        uint256 b0 = _bal(key.currency0, seller);
        uint256 b1 = _bal(key.currency1, seller);

        vm.prank(seller);
        vault.collectFees(id);

        assertEq(uint256(POSM.getPositionLiquidity(tokenId)), uint256(liqBefore));
        assertGe(_bal(key.currency0, seller), b0);
        assertGe(_bal(key.currency1, seller), b1);
        assertEq(POSM.ownerOf(tokenId), address(vault));
        // Nothing may stick to the vault: fees go straight to the lessee.
        if (Currency.unwrap(key.currency0) == address(0)) assertEq(address(vault).balance, 0);
    }

    function test_fork_buyBack_returnsTheNftToTheLessee() public {
        if (!live) return;
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + TERM);
        vm.prank(seller);
        vault.buyBack(id);
        vm.prank(seller);
        vault.withdrawPosition(tokenId);
        assertEq(POSM.ownerOf(tokenId), seller);
        assertEq(vault.balances(financier), uint256(BUYBACK) + RENT);

        uint256 before = USDG.balanceOf(financier);
        vm.prank(financier);
        vault.withdrawUSDG();
        assertEq(USDG.balanceOf(financier), before + BUYBACK + RENT);
    }

    /// The financier's ownership must be real: after taking delivery they can unwind the position.
    function test_fork_release_givesTheFinancierAWorkingPosition() public {
        if (!live) return;
        uint256 id = _listAndFund();
        vm.warp(block.timestamp + TERM + registry.grace());
        vm.prank(financier);
        vault.release(id);
        vm.prank(financier);
        vault.withdrawPosition(tokenId);
        assertEq(POSM.ownerOf(tokenId), financier);

        uint128 liq = POSM.getPositionLiquidity(tokenId);
        uint256 b0 = _bal(key.currency0, financier);
        uint256 b1 = _bal(key.currency1, financier);

        bytes memory actions = abi.encodePacked(Actions.DECREASE_LIQUIDITY, Actions.TAKE_PAIR);
        bytes[] memory params = new bytes[](2);
        params[0] = abi.encode(tokenId, uint256(liq), uint128(0), uint128(0), bytes(""));
        params[1] = abi.encode(key.currency0, key.currency1, financier);
        vm.prank(financier);
        POSM.modifyLiquidities(abi.encode(actions, params), block.timestamp + 60);

        assertEq(uint256(POSM.getPositionLiquidity(tokenId)), 0);
        assertGt(_bal(key.currency0, financier) + _bal(key.currency1, financier), b0 + b1);
    }

    function test_fork_lesseeCannotPullLiquidityWhileLeased() public {
        if (!live) return;
        _listAndFund();
        uint128 liq = POSM.getPositionLiquidity(tokenId);
        bytes memory actions = abi.encodePacked(Actions.DECREASE_LIQUIDITY, Actions.TAKE_PAIR);
        bytes[] memory params = new bytes[](2);
        params[0] = abi.encode(tokenId, uint256(liq), uint128(0), uint128(0), bytes(""));
        params[1] = abi.encode(key.currency0, key.currency1, seller);
        vm.prank(seller);
        vm.expectRevert();
        POSM.modifyLiquidities(abi.encode(actions, params), block.timestamp + 60);
    }
}
