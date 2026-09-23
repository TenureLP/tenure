# Addresses

## Robinhood Chain testnet, 46630

| Contract | Address |
|---|---|
| `LeaseVault` | [`0x27797a2c3428a92c498ed01f3b1c77f636990f7c`](https://explorer.testnet.chain.robinhood.com/address/0x27797a2c3428a92c498ed01f3b1c77f636990f7c) <span class="pill live">live</span> |
| `TestUSDG` (tUSDG) | [`0x182794fbdc0db20341cd61d4d856b0d5101221a4`](https://explorer.testnet.chain.robinhood.com/address/0x182794fbdc0db20341cd61d4d856b0d5101221a4) |
| Uniswap v4 PositionManager | `0x58daec3116aae6D93017bAAea7749052E8a04fA7` |
| Uniswap v4 StateView | `0xF3334192D15450CdD385c8B70e03f9A6bD9E673b` |

Anybody can check the vault is wired to what this page says, with no key:

```bash
cast call 0x27797a2c3428a92c498ed01f3b1c77f636990f7c "posm()(address)"      --rpc-url https://rpc.testnet.chain.robinhood.com
cast call 0x27797a2c3428a92c498ed01f3b1c77f636990f7c "stateView()(address)" --rpc-url https://rpc.testnet.chain.robinhood.com
cast call 0x27797a2c3428a92c498ed01f3b1c77f636990f7c "usdg()(address)"      --rpc-url https://rpc.testnet.chain.robinhood.com
```

RPC `https://rpc.testnet.chain.robinhood.com` · Explorer
[explorer.testnet.chain.robinhood.com](https://explorer.testnet.chain.robinhood.com)

## Robinhood Chain mainnet, 4663

| Contract | Address |
|---|---|
| `LeaseVault` | <span class="pill no">not deployed</span> |
| USDG | `0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168` |
| Uniswap v4 PositionManager | `0x58daec3116aae6D93017bAAea7749052E8a04fA7` |
| Uniswap v4 StateView | `0xF3334192D15450CdD385c8B70e03f9A6bD9E673b` |
| Uniswap v4 PoolManager | `0x8366a39CC670B4001A1121B8F6A443A643e40951` |

RPC `https://rpc.mainnet.chain.robinhood.com` · Explorer
[robinhoodchain.blockscout.com](https://robinhoodchain.blockscout.com)

The testnet carries the same Uniswap v4 deployment at the same addresses as mainnet.
`verify-addresses.sh` checks every one of them against the chain before any deployment: a young chain
redeploys its infrastructure, and the vault cannot tell an empty address from a silent one.

```bash
./verify-addresses.sh            # mainnet
./verify-addresses.sh testnet    # testnet
```
