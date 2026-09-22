# LeaseVault reference

`LeaseVault` is a single immutable contract, Solidity 0.8.28, with no external library. Its constructor
takes three addresses and nothing else:

```solidity
constructor(IERC20 usdg, IPositionManager posm, IStateView stateView)
```

The settlement token, the Uniswap v4 PositionManager, and the v4 StateView. There is nothing to
configure after deployment and nobody to ask.

## Types

```solidity
enum State { None, Listed, Active, BoughtBack, Released, Cancelled }

struct Terms {
    uint128 price;          // what the financier pays
    uint128 rent;           // total rent for the whole term, escrowed from the proceeds
    uint128 buybackPrice;   // never above price
    uint32  term;           // lease duration, seconds
    uint32  grace;          // extra time to buy back after the term
    uint32  listingDuration;// how long the offer stays open
    uint16  maxFrozenBps;   // ceiling on frozen time credited, fraction of the term
    uint8   freezeProbe;    // 0 never checks, 1 calls paused() on both tokens
    address builder;        // who brought the seller, or address(0)
    uint128 builderFee;     // out of the seller's proceeds
}

struct Deal {
    address seller;         // lessee after funding
    address financier;      // owner of the position after funding
    uint256 tokenId;
    bytes32 poolId;
    Currency currency0;
    Currency currency1;
    uint128 price;
    uint128 rent;
    uint128 buybackPrice;
    uint128 rentClaimed;
    uint32  term;
    uint32  grace;
    uint40  listingExpiry;
    uint40  fundedAt;
    uint40  pausedSince;
    uint40  pausedSeenAt;
    uint40  pausedTotal;
    uint16  maxFrozenBps;
    uint8   freezeProbe;
    State   state;
    address builder;
    uint128 builderFee;
}
```

## Constants

| Constant | Value | Meaning |
|---|---|---|
| `MIN_TERM` | 1 day | shortest lease |
| `MAX_TERM` | 30 days | longest lease |
| `MIN_GRACE` | 24 hours | shortest buyback window after the term |
| `MAX_GRACE` | 7 days | longest buyback window after the term |
| `MAX_LISTING_DURATION` | 30 days | longest an offer stays open |
| `MAX_FROZEN_BPS` | 5000 | at most half a term credited as frozen |
| `MAX_FREEZE_GAP` | 6 hours | longest an open freeze counts past its last sighting |
| `MAX_BUILDER_FEE_DIVISOR` | 100 | a builder fee is at most price ÷ 100 |

## Seller

### `list(uint256 tokenId, Terms t) → uint256 dealId`
Offers a position. The NFT must be approved to the vault and moves into it. Checks the terms against
the constants, and the position for liquidity, range and subscriber. Emits `Listed`.

### `cancel(uint256 dealId)`
Withdraws an unfunded listing. The NFT becomes withdrawable by the seller. Emits `Cancelled`.

### `collectFees(uint256 dealId)`
Lessee only, during the term. Collects the swap fees to the lessee's address by decreasing liquidity
by zero and taking both currencies. Emits `FeesCollected`.

### `buyBack(uint256 dealId)`
Lessee only, from funding until `release`. Pulls `buybackPrice` in USDG, credits the financier with it
plus unclaimed rent, refunds unaccrued rent to the lessee, and makes the NFT withdrawable by the lessee.
Emits `BoughtBack`.

## Financier

### `fund(uint256 dealId)`
### `fund(uint256 dealId, address builder, uint128 builderFee)`
Pays `price` (plus the financier's own builder fee) in USDG and becomes the owner. Credits the seller
with `price − rent − builderFee`, escrows the rent and starts the lease. Refused for the seller
(`SelfDeal`), after expiry, or if the position has left its range. Emits `Funded` and `BuilderPaid`.

### `transferFinancierPosition(uint256 dealId, address to)`
Sells the financier's side. Accrued rent is settled to the outgoing financier first. Refuses the zero
address, the vault itself and the seller. Emits `FinancierTransferred`.

### `release(uint256 dealId)`
Financier only, once `term + grace` is over. Credits the remaining accrued rent, refunds anything
unaccrued to the lessee, and makes the NFT withdrawable by the financier. Emits `Released`.

## Anyone

### `claimRent(uint256 dealId)`
Credits accrued rent to the current financier. Emits `RentClaimed`.

### `checkpointFreeze(uint256 dealId)`
Records whether the pair is frozen right now. See [freezes](/concepts/freezes). Emits
`FreezeCheckpoint` when the state changes.

### `withdrawUSDG()`
Sends the caller their whole USDG balance. Emits `WithdrawnUSDG`.

### `withdrawPosition(uint256 tokenId)`
Sends the caller a position NFT owed to them. Emits `WithdrawnPosition`.

## Views

| Function | Returns |
|---|---|
| `deal(dealId)` | the full `Deal` |
| `dealCount()` | number of deals ever listed; ids run from 1 |
| `balances(address)` | USDG withdrawable by an address |
| `positionOwed(tokenId)` | who may withdraw a position NFT |
| `accruedRent(dealId)` | rent accrued so far, net of recorded freezes |
| `leaseEnd(dealId)` | end of the term, far future if unfunded |
| `graceEnd(dealId)` | end of the buyback window, far future if unfunded |
| `usdg()`, `posm()`, `stateView()` | the three addresses it was built with |

## Events

```solidity
event Listed(uint256 indexed dealId, address indexed seller, uint256 indexed tokenId,
             bytes32 poolId, uint128 price, uint128 rent, uint128 buybackPrice,
             uint32 term, uint40 listingExpiry);
event Cancelled(uint256 indexed dealId);
event Funded(uint256 indexed dealId, address indexed financier, uint40 fundedAt);
event BuilderPaid(uint256 indexed dealId, address indexed builder, uint128 fee, bool sellerSide);
event FeesCollected(uint256 indexed dealId, address indexed lessee);
event RentClaimed(uint256 indexed dealId, address indexed financier, uint128 amount);
event BoughtBack(uint256 indexed dealId, uint128 buybackPrice, uint128 rentAccrued, uint128 rentRefunded);
event Released(uint256 indexed dealId, uint128 rentAccrued, uint128 rentRefunded);
event FinancierTransferred(uint256 indexed dealId, address indexed from, address indexed to);
event FreezeCheckpoint(uint256 indexed dealId, bool frozen, uint40 pausedTotal);
event WithdrawnUSDG(address indexed to, uint256 amount);
event WithdrawnPosition(address indexed to, uint256 indexed tokenId);
```

## Source

[`lease-vault/src/LeaseVault.sol`](https://github.com/TenureLP/tenure/blob/main/lease-vault/src/LeaseVault.sol),
635 lines, every design decision commented where it is made.
