// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Currency, PoolKey, PoolIdLib, PoolId} from "../libraries/Types.sol";
import {IStateView} from "../interfaces/IStateView.sol";

/// @dev The test tokens: anyone may mint them, which is what lets this contract pay for positions.
interface IMintableToken {
    function mint(address to, uint256 value) external;
    function approve(address spender, uint256 value) external returns (bool);
    function transfer(address to, uint256 value) external returns (bool);
}

/// @dev Uniswap v4's swap parameters, field for field.
struct SwapParams {
    bool zeroForOne;
    int256 amountSpecified;
    uint160 sqrtPriceLimitX96;
}

/// @dev The part of the v4 PoolManager this contract touches: create the pool, and swap in it.
interface IPoolManagerLite {
    function initialize(PoolKey memory key, uint160 sqrtPriceX96) external returns (int24 tick);
    function unlock(bytes calldata data) external returns (bytes memory);
    function swap(PoolKey memory key, SwapParams memory params, bytes calldata hookData) external returns (int256 delta);
    function sync(Currency currency) external;
    function settle() external payable returns (uint256 paid);
    function take(Currency currency, address to, uint256 amount) external;
}

interface IPermit2Lite {
    function approve(address token, address spender, uint160 amount, uint48 expiration) external;
}

interface IPositionManagerLite {
    function modifyLiquidities(bytes calldata unlockData, uint256 deadline) external payable;
    function nextTokenId() external view returns (uint256);
}

/// @title TestPositionFaucet
/// @notice Hands anybody a live Uniswap v4 position on a test network, in one call.
///
/// @dev Trying Tenure needs a position to lease, and a test network has almost none: nobody
///      provides liquidity where nothing is worth anything. So this contract is the liquidity
///      provider. It owns one pool of two test tokens, and every call to `give()` mints those
///      tokens to itself, opens a position centred on the current price and sends the NFT to the
///      caller. The position is in range and has no subscriber, which is exactly what the vault
///      asks of a listing.
///
///      A pool nobody trades in earns nothing, and "collect the fees" would collect zero. So each
///      call also trades against the pool, a round trip that ends roughly where it started, and
///      pays the swap fee to every position in range, leased ones included. Alternate calls start
///      from alternate sides, so the price does not creep one way.
///
///      Everything here is worthless by construction. It has no owner and holds nothing anybody
///      could want. It exists only on test networks, and its constructor refuses mainnet.
contract TestPositionFaucet {
    using PoolIdLib for PoolKey;

    uint24 public constant FEE = 3000; // 0.3 %
    int24 public constant SPACING = 60;
    /// @notice Ticks either side of the price: about six percent each way.
    int24 public constant HALF_WIDTH = 600;
    uint128 public constant LIQUIDITY = 2e15;

    uint256 internal constant MAINNET = 4663;
    uint256 internal constant Q96 = 2 ** 96;
    int24 internal constant MIN_USABLE_TICK = -887220;
    int24 internal constant MAX_USABLE_TICK = 887220;
    uint160 internal constant MIN_SQRT_PRICE = 4295128739;
    uint160 internal constant MAX_SQRT_PRICE = 1461446703485210103287273052203988822378723970342;

    // PositionManager actions: open a position, then pay for it.
    uint8 internal constant MINT_POSITION = 0x02;
    uint8 internal constant SETTLE_PAIR = 0x0d;

    IPoolManagerLite public immutable poolManager;
    IPositionManagerLite public immutable positionManager;
    IStateView public immutable stateView;
    address public immutable token0;
    address public immutable token1;

    /// @notice Positions handed out so far.
    uint256 public given;

    event Given(address indexed to, uint256 indexed tokenId, int24 tickLower, int24 tickUpper);

    error NotOnMainnet();
    error NotPoolManager();
    error SameToken();

    /// @param sqrtPriceX96 The pool's opening price, token1 per token0, in v4's fixed point. The
    ///        caller sorts the pair; the deploy script works it out from a plain price.
    constructor(
        IPoolManagerLite poolManager_,
        IPositionManagerLite positionManager_,
        IStateView stateView_,
        IPermit2Lite permit2,
        address tokenA,
        address tokenB,
        uint160 sqrtPriceX96
    ) {
        if (block.chainid == MAINNET) revert NotOnMainnet();
        if (tokenA == tokenB) revert SameToken();
        poolManager = poolManager_;
        positionManager = positionManager_;
        stateView = stateView_;
        (token0, token1) = tokenA < tokenB ? (tokenA, tokenB) : (tokenB, tokenA);

        poolManager_.initialize(poolKey(), sqrtPriceX96);

        // The PositionManager takes payment through Permit2, so both hops are approved once, for
        // good. Neither token is worth anything, so an unlimited approval costs nothing here.
        address[2] memory tokens = [token0, token1];
        for (uint256 i; i < 2; ++i) {
            IMintableToken(tokens[i]).approve(address(permit2), type(uint256).max);
            permit2.approve(tokens[i], address(positionManager_), type(uint160).max, type(uint48).max);
        }
    }

    /// @notice The one pool this contract provides liquidity to.
    function poolKey() public view returns (PoolKey memory) {
        return PoolKey(Currency.wrap(token0), Currency.wrap(token1), FEE, SPACING, address(0));
    }

    /// @notice Mints a position around the current price to the caller, then trades against the
    ///         pool so the positions in it have fees to collect.
    /// @return tokenId The new position, owned by the caller.
    function give() external returns (uint256 tokenId) {
        PoolKey memory key = poolKey();
        (uint160 sqrtPriceX96, int24 tick,,) = stateView.getSlot0(PoolId.unwrap(key.toId()));

        // Round the price down to the grid; the price then sits inside [lower, upper).
        int24 base = tick / SPACING * SPACING;
        if (tick < 0 && tick % SPACING != 0) base -= SPACING;
        int24 lower = base - HALF_WIDTH;
        int24 upper = base + HALF_WIDTH;
        if (lower < MIN_USABLE_TICK) lower = MIN_USABLE_TICK;
        if (upper > MAX_USABLE_TICK) upper = MAX_USABLE_TICK;

        // A quarter of L·√P and of L/√P is several times what a range this narrow can take, so the
        // position is always fully paid for. What it does not use funds the trades below.
        IMintableToken(token0).mint(address(this), uint256(LIQUIDITY) * Q96 / sqrtPriceX96 / 4 + 1);
        IMintableToken(token1).mint(address(this), uint256(LIQUIDITY) * sqrtPriceX96 / Q96 / 4 + 1);

        tokenId = positionManager.nextTokenId();
        bytes[] memory params = new bytes[](2);
        params[0] = abi.encode(
            key, lower, upper, uint256(LIQUIDITY), type(uint128).max, type(uint128).max, msg.sender, bytes("")
        );
        params[1] = abi.encode(key.currency0, key.currency1);
        positionManager.modifyLiquidities(abi.encode(abi.encodePacked(MINT_POSITION, SETTLE_PAIR), params), block.timestamp);

        poolManager.unlock(abi.encode(given % 2 == 0));
        unchecked {
            ++given;
        }
        emit Given(msg.sender, tokenId, lower, upper);
    }

    /// @dev The round trip: sell a fortieth of what one position holds of one token, then sell
    ///      back everything that bought. Only the pool manager may call this, and only inside the
    ///      unlock this contract opened.
    function unlockCallback(bytes calldata data) external returns (bytes memory) {
        if (msg.sender != address(poolManager)) revert NotPoolManager();
        bool zeroFirst = abi.decode(data, (bool));
        PoolKey memory key = poolKey();
        (uint160 sqrtPriceX96,,,) = stateView.getSlot0(PoolId.unwrap(key.toId()));

        uint256 amountIn = zeroFirst
            ? uint256(LIQUIDITY) * Q96 / sqrtPriceX96 / 40
            : uint256(LIQUIDITY) * sqrtPriceX96 / Q96 / 40;
        int256 first = poolManager.swap(
            key, SwapParams(zeroFirst, -int256(amountIn), zeroFirst ? MIN_SQRT_PRICE + 1 : MAX_SQRT_PRICE - 1), ""
        );
        int128 bought = zeroFirst ? _amount1(first) : _amount0(first);
        // The pool refuses a swap of nothing, and a first leg that bought nothing leaves nothing
        // to sell back.
        int256 second;
        if (bought > 0) {
            second = poolManager.swap(
                key,
                SwapParams(!zeroFirst, -int256(uint256(uint128(bought))), zeroFirst ? MAX_SQRT_PRICE - 1 : MIN_SQRT_PRICE + 1),
                ""
            );
        }

        _settle(key.currency0, _amount0(first) + _amount0(second));
        _settle(key.currency1, _amount1(first) + _amount1(second));
        return "";
    }

    /// @dev Pays what the round trip owes in a currency, or takes what it is owed.
    function _settle(Currency currency, int128 net) private {
        if (net < 0) {
            poolManager.sync(currency);
            IMintableToken(Currency.unwrap(currency)).transfer(address(poolManager), uint256(uint128(-net)));
            poolManager.settle();
        } else if (net > 0) {
            poolManager.take(currency, address(this), uint256(uint128(net)));
        }
    }

    /// @dev A v4 BalanceDelta packs amount0 in the upper 128 bits and amount1 in the lower.
    function _amount0(int256 delta) private pure returns (int128) {
        return int128(delta >> 128);
    }

    function _amount1(int256 delta) private pure returns (int128) {
        return int128(delta);
    }
}
