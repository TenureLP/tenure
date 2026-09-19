// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @title ScreeningList
/// @notice A published opinion about which Uniswap v4 pools are fit to deal in.
///
/// @dev `LeaseVault` does not read this contract and cannot be made to. It has no power over any
///      deal, it holds no assets, and removing a pool from it stops nothing that is already
///      running. That is the whole point: the vault is a neutral, immutable primitive, and who is
///      willing to deal in what is a judgement that belongs to whoever is parting with money.
///
///      This is one such judgement, published on chain so it can be quoted and audited. A financier
///      may consult it before funding, a vault built on top may refuse anything absent from it, a
///      front end may decline to display the rest. Anyone who disagrees deploys their own and
///      points their own capital at it, which is the freedom a gate welded into the vault would
///      have taken away.
///
///      `screeningRef` is the hash of the report behind an entry. It makes a listing here a claim
///      somebody signed rather than an address somebody typed.
contract ScreeningList {
    struct Pool {
        bool allowed;
        /// @dev 0 = unset, 1 = full-rights tokenised equity, 2 = crypto asset, 3 = other.
        uint8 assetClass;
        /// @dev What this list believes the vault's freeze probe should be set to for this pair.
        ///      0 = do not ask, neither token has a freeze switch worth reading.
        ///      1 = call `paused()` and read one word, 1 meaning frozen.
        ///      Advice, not enforcement: the seller chooses the probe in the deal terms, and with
        ///      probe 1 an answer in any other shape is read as frozen and stops the rent.
        uint8 freezeProbe;
        /// @dev Below this, this list considers a position too small to be worth financing.
        uint128 minLiquidity;
        bytes32 screeningRef; // hash of the screening report for this pair
    }

    address public owner;
    address public pendingOwner;

    mapping(bytes32 poolId => Pool) private _pools;

    event PoolSet(
        bytes32 indexed poolId,
        bool allowed,
        uint8 assetClass,
        uint8 freezeProbe,
        uint128 minLiquidity,
        bytes32 screeningRef
    );
    event OwnershipTransferStarted(address indexed from, address indexed to);
    event OwnershipTransferred(address indexed from, address indexed to);

    error NotOwner();
    error ZeroAddress();
    error BadProbe();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address owner_) {
        if (owner_ == address(0)) revert ZeroAddress();
        owner = owner_;
        emit OwnershipTransferred(address(0), owner_);
    }

    function pool(bytes32 poolId) external view returns (Pool memory) {
        return _pools[poolId];
    }

    /// @notice Record, amend or withdraw this list's opinion of a pool.
    function setPool(
        bytes32 poolId,
        bool allowed,
        uint8 assetClass,
        uint8 freezeProbe,
        uint128 minLiquidity,
        bytes32 screeningRef
    ) external onlyOwner {
        if (freezeProbe > 1) revert BadProbe();
        _pools[poolId] = Pool(allowed, assetClass, freezeProbe, minLiquidity, screeningRef);
        emit PoolSet(poolId, allowed, assetClass, freezeProbe, minLiquidity, screeningRef);
    }

    /// @dev Two steps, so a mistyped address does not silently end the list.
    function transferOwnership(address to) external onlyOwner {
        pendingOwner = to;
        emit OwnershipTransferStarted(owner, to);
    }

    function acceptOwnership() external {
        if (msg.sender != pendingOwner) revert NotOwner();
        emit OwnershipTransferred(owner, msg.sender);
        owner = msg.sender;
        pendingOwner = address(0);
    }
}
