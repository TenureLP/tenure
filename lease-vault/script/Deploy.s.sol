// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {LeaseVault} from "../src/LeaseVault.sol";
import {ScreeningList} from "../src/ScreeningList.sol";
import {IERC20} from "../src/interfaces/IERC20.sol";
import {IPositionManager} from "../src/interfaces/IPositionManager.sol";
import {IStateView} from "../src/interfaces/IStateView.sol";

interface VmScript {
    function envAddress(string calldata name) external view returns (address);
    function envOr(string calldata name, address defaultValue) external view returns (address);
    function startBroadcast() external;
    function stopBroadcast() external;
}

/// @notice Deploys the vault on Robinhood Chain (4663), and optionally a screening list beside it.
/// @dev The vault takes no owner and no parameters beyond the three addresses it reads state from.
///      Once this has run there is nothing left to configure and nobody left to ask: every term of
///      every deal is chosen by its own two parties.
///
///      The screening list is separate on purpose. It is one party publishing an opinion, the vault
///      never reads it, and deploying it is optional. Set SCREENING_OWNER to skip it.
///
///      Canonical addresses on Robinhood Chain mainnet. Confirm every one of them with
///      ../verify-addresses.sh before broadcasting: a young chain redeploys its infrastructure.
contract Deploy {
    VmScript internal constant vm = VmScript(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
    bool public IS_SCRIPT = true;

    address constant USDG = 0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168;
    address constant V4_POSITION_MANAGER = 0x58daec3116aae6D93017bAAea7749052E8a04fA7;
    address constant V4_STATE_VIEW = 0xF3334192D15450CdD385c8B70e03f9A6bD9E673b;

    function run() external returns (LeaseVault vault, ScreeningList list) {
        address screeningOwner = vm.envOr("SCREENING_OWNER", address(0));

        vm.startBroadcast();
        vault = new LeaseVault(IERC20(USDG), IPositionManager(V4_POSITION_MANAGER), IStateView(V4_STATE_VIEW));
        if (screeningOwner != address(0)) {
            list = new ScreeningList(screeningOwner);
        }
        vm.stopBroadcast();
    }
}
