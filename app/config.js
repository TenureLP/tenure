/* What the page talks to, per chain.

   `vault` is what makes a chain usable: empty means nothing is deployed there, and the page says
   so rather than drawing controls that would revert. Filling one in is the whole of going live on
   that chain, and `lease-vault/deploy.sh` prints the line to paste.

   The testnet carries the same Uniswap v4 deployment at the same addresses as the mainnet and has
   no USDG, so its settlement token is whatever `deploy.sh` created there. It also has no valuation
   API: that service prices a position in USDG by reading USDG pools, and there are none to read.
   On a chain with no `api`, the page stops offering to value anything and asks for terms instead. */

window.TENURE = {
  defaultChain: 4663,

  chains: {
    4663: {
      name: "Robinhood Chain",
      rpc: "https://rpc.mainnet.chain.robinhood.com",
      explorer: "https://robinhoodchain.blockscout.com",
      api: "https://api-production-9e87.up.railway.app",

      /* Verified with lease-vault/verify-addresses.sh. A young chain redeploys its
         infrastructure, so these are checked rather than remembered. */
      usdg: "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168",
      usdgSymbol: "USDG",
      usdgDecimals: 6,
      posm: "0x58daec3116aae6D93017bAAea7749052E8a04fA7",

      /* Offered on the empty screen so the first thing a visitor sees is a real answer. Checked
         to be live and quotable; replace it when it stops being either. */
      examples: ["3093793", "3094115"],

      vault: ""
    },

    46630: {
      name: "Robinhood testnet",
      rpc: "https://rpc.testnet.chain.robinhood.com",
      explorer: "https://explorer.testnet.chain.robinhood.com",
      api: null,

      /* Same v4 addresses as the mainnet, checked. The settlement token is a TestUSDG anyone can
         mint, created by the deploy; it is worthless by construction and its name says so. */
      usdg: "0x182794fbdc0db20341cd61d4d856b0d5101221a4",
      usdgSymbol: "tUSDG",
      usdgDecimals: 6,
      posm: "0x58daec3116aae6D93017bAAea7749052E8a04fA7",

      examples: ["5099"],

      /* The settlement token here is TestUSDG, which anyone can mint and which is worth nothing by
         construction. This is what lets the page offer to mint some. Never set it on a chain whose
         token is money: the button would only ever revert there, and it would look like a faucet. */
      testToken: true,

      /* Deployed with lease-vault/deploy.sh on 2026-09-23 and checked against the chain: it
         points at the PositionManager, StateView and TestUSDG above, and has no owner. */
      vault: "0x27797a2c3428a92c498ed01f3b1c77f636990f7c"
    }
  }
};
