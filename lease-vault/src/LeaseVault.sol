// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IERC20} from "./interfaces/IERC20.sol";
import {IPositionManager} from "./interfaces/IPositionManager.sol";
import {IStateView} from "./interfaces/IStateView.sol";
import {SafeERC20} from "./libraries/SafeERC20.sol";
import {Currency, PoolId, PoolKey, PoolIdLib, PositionInfoLib, Actions} from "./libraries/Types.sol";
import {AssetRegistry} from "./AssetRegistry.sol";

/// @title LeaseVault
/// @notice Sale-and-leaseback of Uniswap v4 liquidity positions, with a buyback promise.
///
/// A liquidity provider (the seller, then lessee) sells a position NFT to a financier for a cash
/// price, leases it back for a fixed term against a fixed rent, keeps collecting the swap fees the
/// position earns during the lease (the usufruct), and holds a unilateral promise from the
/// financier to sell the position back at a pre-agreed buyback price. If the lessee does not buy
/// back before the end of the grace window, the financier simply takes delivery of what already
/// belongs to them.
///
/// Design invariants, enforced in code:
///  - Ownership really transfers at funding: the financier can sell their ownership on, and bears
///    the asset risk (rent stops accruing while the underlying token is frozen; if the position is
///    destroyed the financier has no claim on the lessee).
///  - The lessee can only collect fees; liquidity can never be decreased during the lease.
///  - Rent is prepaid into escrow and streamed per usable second. Unaccrued rent is refunded on
///    early buyback and on frozen periods. Rent is a fixed amount, never compounding.
///  - The protocol fee is a flat amount snapshotted at listing, never a percentage.
///  - No oracle, no liquidation, no forced sale. All payouts are pull-based balances.
///  - The seller can never be the financier of their own deal.
///
/// The contract has no owner and no upgrade path. The only external policy input is the registry,
/// read at listing time and snapshotted into the deal.
contract LeaseVault {
    using SafeERC20 for IERC20;
    using PoolIdLib for PoolKey;
    using PositionInfoLib for uint256;

    // ---------------------------------------------------------------------
    // Types
    // ---------------------------------------------------------------------

    enum State {
        None,
        Listed,
        Active,
        BoughtBack,
        Released,
        Cancelled
    }

    struct Deal {
        address seller; // lessee after funding
        address financier; // owner of the position after funding
        uint256 tokenId;
        bytes32 poolId;
        Currency currency0;
        Currency currency1;
        uint128 price; // sale price paid by the financier
        uint128 rent; // total rent for the full term, prepaid from proceeds
        uint128 buybackPrice; // price at which the financier promises to sell back
        uint128 listingFee; // flat protocol fee snapshotted at listing
        uint128 rentClaimed; // rent already credited to the financier
        uint32 term;
        uint32 grace;
        uint40 listingExpiry;
        uint40 fundedAt;
        uint40 pausedSince; // non-zero while a freeze of the underlying is recorded
        uint40 pausedTotal; // cumulative frozen seconds already closed
        State state;
    }

    // ---------------------------------------------------------------------
    // Immutables / storage
    // ---------------------------------------------------------------------

    IERC20 public immutable usdg;
    IPositionManager public immutable posm;
    IStateView public immutable stateView;
    AssetRegistry public immutable registry;

    uint256 public dealCount;
    mapping(uint256 dealId => Deal) private _deals;

    /// @notice USDG owed to an address, withdrawable at any time.
    mapping(address => uint256) public balances;
    /// @notice Address entitled to withdraw a given position NFT.
    mapping(uint256 tokenId => address) public positionOwed;

    uint256 private _lock = 1;

    // ---------------------------------------------------------------------
    // Events / errors
    // ---------------------------------------------------------------------

    event Listed(
        uint256 indexed dealId,
        address indexed seller,
        uint256 indexed tokenId,
        bytes32 poolId,
        uint128 price,
        uint128 rent,
        uint128 buybackPrice,
        uint32 term,
        uint40 listingExpiry
    );
    event Cancelled(uint256 indexed dealId);
    event Funded(uint256 indexed dealId, address indexed financier, uint40 fundedAt, uint128 listingFee);
    event FeesCollected(uint256 indexed dealId, address indexed lessee);
    event RentClaimed(uint256 indexed dealId, address indexed financier, uint128 amount);
    event BoughtBack(uint256 indexed dealId, uint128 buybackPrice, uint128 rentAccrued, uint128 rentRefunded);
    event Released(uint256 indexed dealId, uint128 rentAccrued, uint128 rentRefunded);
    event FinancierTransferred(uint256 indexed dealId, address indexed from, address indexed to);
    event FreezeCheckpoint(uint256 indexed dealId, bool frozen, uint40 pausedTotal);
    event WithdrawnUSDG(address indexed to, uint256 amount);
    event WithdrawnPosition(address indexed to, uint256 indexed tokenId);

    error Reentrancy();
    error ListingsPaused();
    error TermNotAllowed();
    error BadListingDuration();
    error BadEconomics();
    error PoolNotAllowed();
    error HasSubscriber();
    error LiquidityTooLow();
    error OutOfRange();
    error NotListed();
    error NotActive();
    error ListingExpired();
    error SelfDeal();
    error NotSeller();
    error NotFinancier();
    error LeaseEnded();
    error GraceNotOver();
    error NothingOwed();
    error ZeroAddress();
    error PositionNotHeld();

    modifier nonReentrant() {
        if (_lock != 1) revert Reentrancy();
        _lock = 2;
        _;
        _lock = 1;
    }

    constructor(IERC20 usdg_, IPositionManager posm_, IStateView stateView_, AssetRegistry registry_) {
        if (
            address(usdg_) == address(0) || address(posm_) == address(0) || address(stateView_) == address(0)
                || address(registry_) == address(0)
        ) revert ZeroAddress();
        usdg = usdg_;
        posm = posm_;
        stateView = stateView_;
        registry = registry_;
    }

    // ---------------------------------------------------------------------
    // Views
    // ---------------------------------------------------------------------

    function deal(uint256 dealId) external view returns (Deal memory) {
        return _deals[dealId];
    }

    /// @notice Rent accrued so far for the financier, net of recorded frozen periods.
    /// @dev Does not account for a freeze that started after the last checkpoint; call
    ///      checkpointFreeze first for an exact figure.
    function accruedRent(uint256 dealId) external view returns (uint128) {
        Deal storage d = _deals[dealId];
        if (d.state != State.Active) return d.rentClaimed;
        return _accrued(d);
    }

    function leaseEnd(uint256 dealId) public view returns (uint40) {
        Deal storage d = _deals[dealId];
        return d.fundedAt + d.term;
    }

    function graceEnd(uint256 dealId) public view returns (uint40) {
        Deal storage d = _deals[dealId];
        return d.fundedAt + d.term + d.grace;
    }

    // ---------------------------------------------------------------------
    // Listing
    // ---------------------------------------------------------------------

    /// @notice Offer a position for sale-and-leaseback.
    /// @param tokenId         Uniswap v4 PositionManager NFT, approved to this vault.
    /// @param price           Sale price the financier pays (USDG raw units).
    /// @param rent            Total rent for the whole term, deducted from proceeds and escrowed.
    /// @param buybackPrice    Price at which the financier promises to sell the position back.
    /// @param term            Lease duration in seconds, must be allowlisted by the registry.
    /// @param listingDuration Seconds the listing stays open for funding.
    function list(
        uint256 tokenId,
        uint128 price,
        uint128 rent,
        uint128 buybackPrice,
        uint32 term,
        uint32 listingDuration
    ) external nonReentrant returns (uint256 dealId) {
        if (registry.listingsPaused()) revert ListingsPaused();
        if (!registry.isTermAllowed(term)) revert TermNotAllowed();
        if (listingDuration == 0 || listingDuration > registry.maxListingDuration()) revert BadListingDuration();
        uint128 fee = registry.listingFee();
        if (price == 0 || uint256(rent) + fee >= price) revert BadEconomics();

        dealId = ++dealCount;
        Deal storage d = _deals[dealId];
        (d.poolId, d.currency0, d.currency1) = _checkEligible(tokenId);

        posm.transferFrom(msg.sender, address(this), tokenId);
        if (posm.ownerOf(tokenId) != address(this)) revert PositionNotHeld();

        d.seller = msg.sender;
        d.tokenId = tokenId;
        d.price = price;
        d.rent = rent;
        d.buybackPrice = buybackPrice;
        d.listingFee = fee;
        d.term = term;
        d.grace = registry.grace();
        d.listingExpiry = uint40(block.timestamp + listingDuration);
        d.state = State.Listed;

        _emitListed(dealId);
    }

    /// @dev Admission checks: allowlisted pool, no subscriber, enough liquidity, in range.
    function _checkEligible(uint256 tokenId) private view returns (bytes32 poolId, Currency c0, Currency c1) {
        (PoolKey memory key, uint256 info) = posm.getPoolAndPositionInfo(tokenId);
        poolId = PoolId.unwrap(key.toId());
        AssetRegistry.PoolConfig memory cfg = registry.poolConfig(poolId);
        if (!cfg.allowed) revert PoolNotAllowed();
        if (info.hasSubscriber()) revert HasSubscriber();
        if (posm.getPositionLiquidity(tokenId) < cfg.minLiquidity) revert LiquidityTooLow();
        (, int24 tick,,) = stateView.getSlot0(poolId);
        if (tick < info.tickLower() || tick >= info.tickUpper()) revert OutOfRange();
        return (poolId, key.currency0, key.currency1);
    }

    function _emitListed(uint256 dealId) private {
        Deal storage d = _deals[dealId];
        emit Listed(
            dealId, d.seller, d.tokenId, d.poolId, d.price, d.rent, d.buybackPrice, d.term, d.listingExpiry
        );
    }

    /// @notice Withdraw an unfunded listing. The NFT becomes withdrawable by the seller.
    function cancel(uint256 dealId) external nonReentrant {
        Deal storage d = _deals[dealId];
        if (d.state != State.Listed) revert NotListed();
        if (msg.sender != d.seller) revert NotSeller();
        d.state = State.Cancelled;
        positionOwed[d.tokenId] = d.seller;
        emit Cancelled(dealId);
    }

    // ---------------------------------------------------------------------
    // Sale + lease
    // ---------------------------------------------------------------------

    /// @notice Buy the position at the listed price and lease it back to the seller.
    /// @dev Two legal acts settle here in order: the sale (price paid, ownership recorded to the
    ///      financier) then the lease (rent escrowed, lease clock started).
    function fund(uint256 dealId) external nonReentrant {
        Deal storage d = _deals[dealId];
        if (d.state != State.Listed) revert NotListed();
        if (block.timestamp > d.listingExpiry) revert ListingExpired();
        if (msg.sender == d.seller) revert SelfDeal();

        usdg.safeTransferFrom(msg.sender, address(this), d.price);

        d.financier = msg.sender;
        d.fundedAt = uint40(block.timestamp);
        d.state = State.Active;

        // Sale proceeds to the seller, net of the prepaid rent and the flat fee.
        balances[d.seller] += uint256(d.price) - d.rent - d.listingFee;
        balances[registry.feeRecipient()] += d.listingFee;
        // The rent stays in the vault as escrow and streams to the financier.

        _checkpoint(d, dealId);
        emit Funded(dealId, msg.sender, d.fundedAt, d.listingFee);
    }

    /// @notice Lessee collects the swap fees earned by the position. Liquidity is never touched.
    function collectFees(uint256 dealId) external nonReentrant {
        Deal storage d = _deals[dealId];
        if (d.state != State.Active) revert NotActive();
        if (msg.sender != d.seller) revert NotSeller();
        if (block.timestamp > d.fundedAt + d.term) revert LeaseEnded();
        _checkpoint(d, dealId);

        bytes memory actions = abi.encodePacked(Actions.DECREASE_LIQUIDITY, Actions.TAKE_PAIR);
        bytes[] memory params = new bytes[](2);
        params[0] = abi.encode(d.tokenId, uint256(0), uint128(0), uint128(0), bytes(""));
        params[1] = abi.encode(d.currency0, d.currency1, d.seller);
        posm.modifyLiquidities(abi.encode(actions, params), block.timestamp);

        emit FeesCollected(dealId, d.seller);
    }

    /// @notice Credit the financier with rent accrued so far. Callable by anyone.
    function claimRent(uint256 dealId) external nonReentrant {
        Deal storage d = _deals[dealId];
        if (d.state != State.Active) revert NotActive();
        _checkpoint(d, dealId);
        uint128 accrued = _accrued(d);
        uint128 owed = accrued - d.rentClaimed;
        if (owed == 0) revert NothingOwed();
        d.rentClaimed = accrued;
        balances[d.financier] += owed;
        emit RentClaimed(dealId, d.financier, owed);
    }

    /// @notice Lessee exercises the promise of the financier and buys the position back.
    /// @dev Allowed from funding until the financier takes delivery after grace. Unaccrued rent
    ///      is refunded because the lease ends with the transfer of ownership.
    function buyBack(uint256 dealId) external nonReentrant {
        Deal storage d = _deals[dealId];
        if (d.state != State.Active) revert NotActive();
        if (msg.sender != d.seller) revert NotSeller();
        _checkpoint(d, dealId);

        usdg.safeTransferFrom(msg.sender, address(this), d.buybackPrice);

        uint128 accrued = _accrued(d);
        uint128 owedToFinancier = accrued - d.rentClaimed;
        uint128 refund = d.rent - accrued;
        d.rentClaimed = accrued;
        d.state = State.BoughtBack;

        balances[d.financier] += uint256(d.buybackPrice) + owedToFinancier;
        balances[d.seller] += refund;
        positionOwed[d.tokenId] = d.seller;

        emit BoughtBack(dealId, d.buybackPrice, accrued, refund);
    }

    /// @notice After the grace window, the financier takes delivery of the position they own.
    function release(uint256 dealId) external nonReentrant {
        Deal storage d = _deals[dealId];
        if (d.state != State.Active) revert NotActive();
        if (msg.sender != d.financier) revert NotFinancier();
        if (block.timestamp < d.fundedAt + d.term + d.grace) revert GraceNotOver();
        _checkpoint(d, dealId);

        uint128 accrued = _accrued(d);
        uint128 owedToFinancier = accrued - d.rentClaimed;
        uint128 refund = d.rent - accrued;
        d.rentClaimed = accrued;
        d.state = State.Released;

        balances[d.financier] += owedToFinancier;
        balances[d.seller] += refund;
        positionOwed[d.tokenId] = d.financier;

        emit Released(dealId, accrued, refund);
    }

    /// @notice The financier sells their ownership of the leased position. The lease continues.
    function transferFinancierPosition(uint256 dealId, address to) external nonReentrant {
        Deal storage d = _deals[dealId];
        if (d.state != State.Active) revert NotActive();
        if (msg.sender != d.financier) revert NotFinancier();
        if (to == address(0)) revert ZeroAddress();
        if (to == d.seller) revert SelfDeal();
        _checkpoint(d, dealId);
        // Settle accrued rent to the outgoing financier first.
        uint128 accrued = _accrued(d);
        uint128 owed = accrued - d.rentClaimed;
        if (owed != 0) {
            d.rentClaimed = accrued;
            balances[d.financier] += owed;
            emit RentClaimed(dealId, d.financier, owed);
        }
        emit FinancierTransferred(dealId, d.financier, to);
        d.financier = to;
    }

    /// @notice Record a freeze / unfreeze of the underlying token. Callable by anyone (keepers).
    function checkpointFreeze(uint256 dealId) external {
        Deal storage d = _deals[dealId];
        if (d.state != State.Active) revert NotActive();
        _checkpoint(d, dealId);
    }

    // ---------------------------------------------------------------------
    // Withdrawals (pull-based)
    // ---------------------------------------------------------------------

    function withdrawUSDG() external nonReentrant {
        uint256 amount = balances[msg.sender];
        if (amount == 0) revert NothingOwed();
        balances[msg.sender] = 0;
        usdg.safeTransfer(msg.sender, amount);
        emit WithdrawnUSDG(msg.sender, amount);
    }

    function withdrawPosition(uint256 tokenId) external nonReentrant {
        if (positionOwed[tokenId] != msg.sender) revert NothingOwed();
        delete positionOwed[tokenId];
        posm.transferFrom(address(this), msg.sender, tokenId);
        emit WithdrawnPosition(msg.sender, tokenId);
    }

    // ---------------------------------------------------------------------
    // Internal: rent accounting
    // ---------------------------------------------------------------------

    /// @dev Current time clamped to the end of the lease.
    function _clampedNow(Deal storage d) private view returns (uint40) {
        uint40 end = d.fundedAt + d.term;
        return block.timestamp >= end ? end : uint40(block.timestamp);
    }

    /// @dev Rent accrues only for usable seconds: elapsed minus recorded frozen time.
    function _accrued(Deal storage d) private view returns (uint128) {
        uint40 t = _clampedNow(d);
        uint256 usable = uint256(t - d.fundedAt) - d.pausedTotal - (d.pausedSince != 0 ? (t - d.pausedSince) : 0);
        return uint128(uint256(d.rent) * usable / d.term);
    }

    function _checkpoint(Deal storage d, uint256 dealId) private {
        uint40 t = _clampedNow(d);
        bool frozen = _isFrozen(d);
        if (frozen) {
            if (d.pausedSince == 0) {
                d.pausedSince = t;
                emit FreezeCheckpoint(dealId, true, d.pausedTotal);
            }
        } else if (d.pausedSince != 0) {
            d.pausedTotal += t - d.pausedSince;
            d.pausedSince = 0;
            emit FreezeCheckpoint(dealId, false, d.pausedTotal);
        }
    }

    /// @dev Best-effort detection of an issuer / regulator freeze on either side of the pair.
    function _isFrozen(Deal storage d) private view returns (bool) {
        return _paused(Currency.unwrap(d.currency0)) || _paused(Currency.unwrap(d.currency1));
    }

    function _paused(address token) private view returns (bool) {
        if (token == address(0)) return false; // native currency
        (bool ok, bytes memory ret) = token.staticcall(abi.encodeWithSignature("paused()"));
        return ok && ret.length == 32 && abi.decode(ret, (uint256)) == 1;
    }
}
