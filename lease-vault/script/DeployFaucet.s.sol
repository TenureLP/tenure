// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {TestToken} from "../src/testnet/TestToken.sol";
import {
    TestPositionFaucet,
    IPoolManagerLite,
    IPositionManagerLite,
    IPermit2Lite
} from "../src/testnet/TestPositionFaucet.sol";
import {IStateView} from "../src/interfaces/IStateView.sol";

interface VmFaucetScript {
    function envOr(string calldata name, address defaultValue) external view returns (address);
    function startBroadcast() external;
    function stopBroadcast() external;
}

interface IPositionManagerMeta {
    function poolManager() external view returns (address);
    function permit2() external view returns (address);
}

/// @notice The pool's opening price, 3,000 tUSDG per tETH, in Uniswap v4's fixed point.
/// @dev v4 quotes token1 per token0 in raw units, so which side is which depends on how the two
///      addresses sort. Shared with the fork test so both open the pool the same way.
library OpeningPrice {
    uint256 internal constant TUSDG_PER_TETH = 3000e6; // six decimals
    uint256 internal constant ONE_TETH = 1e18; // eighteen

    function sqrtPriceX96(address teth, address tusdg) internal pure returns (uint160) {
        uint256 ratioX192 = teth < tusdg
            ? (TUSDG_PER_TETH << 192) / ONE_TETH // tETH is token0
            : (ONE_TETH << 192) / TUSDG_PER_TETH; // tUSDG is token0
        return uint160(_sqrt(ratioX192));
    }

    /// @dev Integer square root, rounded down. Newton's method from a power-of-two first guess.
    function _sqrt(uint256 x) private pure returns (uint256 y) {
        if (x == 0) return 0;
        uint256 z = 1 << ((_log2(x) >> 1) + 1);
        y = z;
        while (true) {
            z = (x / y + y) >> 1;
            if (z >= y) return y;
            y = z;
        }
    }

    function _log2(uint256 x) private pure returns (uint256 n) {
        while (x > 1) {
            x >>= 1;
            ++n;
        }
    }
}

/// @notice Deploys the second test token and the position faucet, on a test network only.
/// @dev Run after Deploy.s.sol, with TUSDG set to the TestUSDG that deploy created. The faucet
///      opens its pool in its own constructor, so once this has run the pool exists and the first
///      `give()` already returns a position the vault will accept.
contract DeployFaucet {
    VmFaucetScript internal constant vm = VmFaucetScript(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
    bool public IS_SCRIPT = true;

    address constant DEFAULT_POSITION_MANAGER = 0x58daec3116aae6D93017bAAea7749052E8a04fA7;
    address constant DEFAULT_STATE_VIEW = 0xF3334192D15450CdD385c8B70e03f9A6bD9E673b;
    /// @dev The one deploy.sh created on Robinhood Chain testnet, 46630.
    address constant TESTNET_TUSDG = 0x182794FbDc0Db20341cd61D4D856b0D5101221A4;

    error NoCodeAt(address);

    function run() external returns (TestToken teth, TestPositionFaucet faucet) {
        address tusdg = vm.envOr("TUSDG", TESTNET_TUSDG);
        address posm = vm.envOr("V4_POSITION_MANAGER", DEFAULT_POSITION_MANAGER);
        address stateView = vm.envOr("V4_STATE_VIEW", DEFAULT_STATE_VIEW);
        _requireCode(tusdg);
        _requireCode(posm);
        _requireCode(stateView);
        address poolManager = IPositionManagerMeta(posm).poolManager();
        address permit2 = IPositionManagerMeta(posm).permit2();
        _requireCode(poolManager);
        _requireCode(permit2);

        vm.startBroadcast();
        teth = new TestToken("Test Ether (worthless)", "tETH", 18);
        faucet = new TestPositionFaucet(
            IPoolManagerLite(poolManager),
            IPositionManagerLite(posm),
            IStateView(stateView),
            IPermit2Lite(permit2),
            address(teth),
            tusdg,
            OpeningPrice.sqrtPriceX96(address(teth), tusdg)
        );
        vm.stopBroadcast();
    }

    function _requireCode(address a) private view {
        uint256 size;
        assembly ("memory-safe") {
            size := extcodesize(a)
        }
        if (size == 0) revert NoCodeAt(a);
    }
}
