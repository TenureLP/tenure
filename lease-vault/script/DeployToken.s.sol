// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {TenureToken} from "../src/TenureToken.sol";

interface VmScript {
    function envAddress(string calldata name) external view returns (address);
    function envOr(string calldata name, uint256 defaultValue) external view returns (uint256);
    function startBroadcast() external;
    function stopBroadcast() external;
}

/// @notice Deploys the token. Deliberately its own script.
/// @dev The token is not part of the protocol and the protocol does not read it: `LeaseVault` takes
///      no fee, holds no reference to it, and behaves identically whether this is ever deployed.
///      Deploying them together would suggest a relationship that does not exist.
///
///      TOKEN_RECIPIENT receives the entire supply. Where it goes afterwards is the only thing that
///      matters to anybody buying, and no constructor can make that honest. Publish it in
///      docs/TOKEN.md before asking anyone for money.
contract DeployToken {
    VmScript internal constant vm = VmScript(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
    bool public IS_SCRIPT = true;

    function run() external returns (TenureToken token) {
        address recipient = vm.envAddress("TOKEN_RECIPIENT");
        uint256 supply = vm.envOr("TOKEN_SUPPLY", uint256(1_000_000_000 ether));

        vm.startBroadcast();
        token = new TenureToken(recipient, supply);
        vm.stopBroadcast();
    }
}
