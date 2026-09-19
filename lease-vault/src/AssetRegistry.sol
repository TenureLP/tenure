// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @title AssetRegistry
/// @notice Owner-managed allowlist of Uniswap v4 pools and economic parameters for the LeaseVault.
/// @dev The registry never touches deals or assets. Everything it controls is read by the vault at
///      listing time and snapshotted into the deal, so a later change never alters an active deal.
contract AssetRegistry {
    // ---------------------------------------------------------------------
    // Types
    // ---------------------------------------------------------------------

    /// @dev Documentation-only classification, surfaced to the UI and the screening committee.
    ///      0 = unset, 1 = full-rights tokenized equity, 2 = crypto asset, 3 = other.
    struct PoolConfig {
        bool allowed;
        uint8 assetClass;
        /// @dev How the vault should ask this pair whether it is frozen.
        ///      0 = do not ask, neither token has a freeze switch worth reading.
        ///      1 = call `paused()` and read one word, 1 meaning frozen.
        ///      Set it only after checking what the tokens actually return: with probe 1, an answer
        ///      in any other shape is read as frozen and stops the rent.
        uint8 freezeProbe;
        uint128 minLiquidity;
        bytes32 screeningRef; // e.g. hash of the asset screening report for this pair
    }

    // ---------------------------------------------------------------------
    // Constants
    // ---------------------------------------------------------------------

    uint32 public constant MIN_TERM = 1 days;
    uint32 public constant MAX_TERM = 30 days;
    uint32 public constant MIN_GRACE = 24 hours;
    uint32 public constant MAX_GRACE = 7 days;
    uint32 public constant MAX_MAX_LISTING_DURATION = 30 days;

    /// @notice Hard cap on the flat listing fee, fixed at deployment (USDG raw units).
    uint128 public immutable MAX_LISTING_FEE;

    // ---------------------------------------------------------------------
    // Storage
    // ---------------------------------------------------------------------

    address public owner;
    address public pendingOwner;

    mapping(bytes32 poolId => PoolConfig) private _pools;
    mapping(uint32 term => bool) public termAllowed;

    uint32 public grace = 48 hours;
    uint32 public maxListingDuration = 7 days;
    uint128 public listingFee; // flat amount, never a percentage
    address public feeRecipient;
    bool public listingsPaused;

    // ---------------------------------------------------------------------
    // Events / errors
    // ---------------------------------------------------------------------

    event PoolSet(
        bytes32 indexed poolId, bool allowed, uint8 assetClass, uint8 freezeProbe, uint128 minLiquidity, bytes32 screeningRef
    );
    event TermSet(uint32 term, bool allowed);
    event GraceSet(uint32 grace);
    event MaxListingDurationSet(uint32 duration);
    event ListingFeeSet(uint128 fee);
    event FeeRecipientSet(address recipient);
    event ListingsPausedSet(bool paused);
    event OwnershipTransferStarted(address indexed from, address indexed to);
    event OwnershipTransferred(address indexed from, address indexed to);

    error NotOwner();
    error NotPendingOwner();
    error BadTerm();
    error BadGrace();
    error BadDuration();
    error FeeAboveCap();
    error ZeroAddress();
    error BadProbe();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address owner_, address feeRecipient_, uint128 maxListingFee) {
        if (owner_ == address(0) || feeRecipient_ == address(0)) revert ZeroAddress();
        owner = owner_;
        feeRecipient = feeRecipient_;
        MAX_LISTING_FEE = maxListingFee;
        emit OwnershipTransferred(address(0), owner_);
    }

    // ---------------------------------------------------------------------
    // Views
    // ---------------------------------------------------------------------

    function poolConfig(bytes32 poolId) external view returns (PoolConfig memory) {
        return _pools[poolId];
    }

    function isTermAllowed(uint32 term) external view returns (bool) {
        return termAllowed[term];
    }

    // ---------------------------------------------------------------------
    // Owner actions
    // ---------------------------------------------------------------------

    function setPool(
        bytes32 poolId,
        bool allowed,
        uint8 assetClass,
        uint8 freezeProbe,
        uint128 minLiquidity,
        bytes32 screeningRef
    ) external onlyOwner {
        if (freezeProbe > 1) revert BadProbe();
        _pools[poolId] = PoolConfig({
            allowed: allowed,
            assetClass: assetClass,
            freezeProbe: freezeProbe,
            minLiquidity: minLiquidity,
            screeningRef: screeningRef
        });
        emit PoolSet(poolId, allowed, assetClass, freezeProbe, minLiquidity, screeningRef);
    }

    function setTerm(uint32 term, bool allowed) external onlyOwner {
        if (term < MIN_TERM || term > MAX_TERM) revert BadTerm();
        termAllowed[term] = allowed;
        emit TermSet(term, allowed);
    }

    function setGrace(uint32 grace_) external onlyOwner {
        if (grace_ < MIN_GRACE || grace_ > MAX_GRACE) revert BadGrace();
        grace = grace_;
        emit GraceSet(grace_);
    }

    function setMaxListingDuration(uint32 duration) external onlyOwner {
        if (duration == 0 || duration > MAX_MAX_LISTING_DURATION) revert BadDuration();
        maxListingDuration = duration;
        emit MaxListingDurationSet(duration);
    }

    function setListingFee(uint128 fee) external onlyOwner {
        if (fee > MAX_LISTING_FEE) revert FeeAboveCap();
        listingFee = fee;
        emit ListingFeeSet(fee);
    }

    function setFeeRecipient(address recipient) external onlyOwner {
        if (recipient == address(0)) revert ZeroAddress();
        feeRecipient = recipient;
        emit FeeRecipientSet(recipient);
    }

    function setListingsPaused(bool paused) external onlyOwner {
        listingsPaused = paused;
        emit ListingsPausedSet(paused);
    }

    function transferOwnership(address to) external onlyOwner {
        pendingOwner = to;
        emit OwnershipTransferStarted(owner, to);
    }

    function acceptOwnership() external {
        if (msg.sender != pendingOwner) revert NotPendingOwner();
        emit OwnershipTransferred(owner, msg.sender);
        owner = msg.sender;
        pendingOwner = address(0);
    }
}
