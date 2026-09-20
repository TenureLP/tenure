// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {LeaseVault} from "../src/LeaseVault.sol";
import {ScreeningList} from "../src/ScreeningList.sol";
import {TestUSDG} from "../src/TestUSDG.sol";
import {IERC20} from "../src/interfaces/IERC20.sol";
import {IPositionManager} from "../src/interfaces/IPositionManager.sol";
import {IStateView} from "../src/interfaces/IStateView.sol";

interface VmScript {
    function envAddress(string calldata name) external view returns (address);
    function envOr(string calldata name, address defaultValue) external view returns (address);
    function startBroadcast() external;
    function stopBroadcast() external;
}

/// @notice Deploys the vault, on Robinhood Chain or on its testnet.
/// @dev The vault takes no owner and no parameters beyond the three addresses it reads state from.
///      Once this has run there is nothing left to configure and nobody left to ask: every term of
///      every deal is chosen by its own two parties.
///
///      The three addresses default to the canonical ones on Robinhood Chain mainnet and can each
///      be overridden by environment variable. They are defaults rather than constants because the
///      testnet carries the same Uniswap v4 deployment at the same addresses but has no USDG, so
///      the settlement token is the one thing that genuinely differs between the two chains.
///      Confirm every address with ../verify-addresses.sh before broadcasting: a young chain
///      redeploys its infrastructure.
///
///      Leave USDG unset and this deploys a TestUSDG anyone can mint, which is the only way to
///      exercise the vault on a chain that has no settlement token. It refuses to do that on
///      chain 4663, because a worthless token beside a real one is how somebody loses money by
///      copying the wrong address out of a deploy log.
///
///      The screening list is separate on purpose. It is one party publishing an opinion, the
///      vault never reads it, and deploying it is optional. Leave SCREENING_OWNER unset to skip it.
contract Deploy {
    VmScript internal constant vm = VmScript(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
    bool public IS_SCRIPT = true;

    uint256 constant MAINNET = 4663;

    address constant DEFAULT_USDG = 0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168;
    address constant DEFAULT_POSITION_MANAGER = 0x58daec3116aae6D93017bAAea7749052E8a04fA7;
    address constant DEFAULT_STATE_VIEW = 0xF3334192D15450CdD385c8B70e03f9A6bD9E673b;

    error NoCodeAt(address);

    function run() external returns (LeaseVault vault, ScreeningList list, TestUSDG testToken) {
        address usdg = vm.envOr("USDG", address(0));
        address posm = vm.envOr("V4_POSITION_MANAGER", DEFAULT_POSITION_MANAGER);
        address stateView = vm.envOr("V4_STATE_VIEW", DEFAULT_STATE_VIEW);
        address screeningOwner = vm.envOr("SCREENING_OWNER", address(0));

        // The vault calls these two and cannot tell an empty address from a silent one, so the
        // deploy stops here rather than producing a vault that reverts on its first listing.
        _requireCode(posm);
        _requireCode(stateView);
        if (usdg != address(0)) _requireCode(usdg);

        vm.startBroadcast();

        if (usdg == address(0)) {
            // Mainnet has a settlement token already and it is not this script's to invent, so an
            // unset variable there means "the usual one" and never "make one up". Everywhere else
            // it means there is nothing to settle in yet, which is what TestUSDG is for.
            if (block.chainid == MAINNET) {
                usdg = DEFAULT_USDG;
                _requireCode(usdg);
            } else {
                testToken = new TestUSDG();
                usdg = address(testToken);
            }
        }

        vault = new LeaseVault(IERC20(usdg), IPositionManager(posm), IStateView(stateView));
        if (screeningOwner != address(0)) list = new ScreeningList(screeningOwner);

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
