/* What the page talks to. The only file that has to change between one deployment and the next.

   `vault` is empty because no LeaseVault is deployed on any chain. The page reads that emptiness
   and shows the valuation screen alone rather than controls that would revert. Filling it in is
   the whole of "going live" for this front end. */

window.TENURE = {
  api: "https://api-production-9e87.up.railway.app",

  chain: {
    id: 4663,
    name: "Robinhood Chain",
    rpc: "https://rpc.mainnet.chain.robinhood.com",
    explorer: "https://robinhoodchain.blockscout.com"
  },

  /* Verified with lease-vault/verify-addresses.sh. A young chain redeploys its infrastructure,
     so these are checked rather than remembered. */
  usdg: "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168",
  usdgDecimals: 6,
  posm: "0x58daec3116aae6D93017bAAea7749052E8a04fA7",

  vault: ""
};
