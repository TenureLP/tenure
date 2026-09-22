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

      vault: ""
    },

    46630: {
      name: "Robinhood testnet",
      rpc: "https://rpc.testnet.chain.robinhood.com",
      explorer: "https://explorer.testnet.chain.robinhood.com",
      api: null,

      /* Same v4 addresses as the mainnet, checked. The settlement token is a TestUSDG anyone can
         mint, created by the deploy; it is worthless by construction and its name says so. */
      usdg: "",
      usdgSymbol: "tUSDG",
      usdgDecimals: 6,
      posm: "0x58daec3116aae6D93017bAAea7749052E8a04fA7",

      vault: ""
    }
  }
};
