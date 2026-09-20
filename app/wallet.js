/* The wallet, and the one place a transaction is sent from.

   Reads never come through here: the page works with no wallet at all, over plain JSON-RPC, so
   somebody can look at a deal before deciding whether to have an opinion about it. Only the four
   acts that change something — list, fund, collect, buy back — need a key, and a key belongs in
   the wallet and nowhere else.

   Every send is dry-run with eth_call first. A revert costs nothing to discover that way and the
   vault answers with a named error, so "the transaction failed" becomes "the buyback is above the
   sale price" before anybody pays for a block. */

window.Wallet = (function () {
  "use strict";

  var cfg = null;          // set by init()
  var provider = null;     // EIP-1193, the browser's or the development shim
  var listeners = [];

  var state = {
    account: null,
    chainId: null,
    kind: null             // "injected" | "dev"
  };

  function emit() {
    listeners.forEach(function (fn) { fn(state); });
  }

  function on(fn) {
    listeners.push(fn);
    fn(state);
  }

  // ------------------------------------------------------------------ the development shim
  //
  // Anvil holds the keys of its own test accounts and will sign for them, so a page pointed at a
  // forked chain can exercise every write path without a browser extension. It exists only when
  // the page is served from this machine and the url asks for it by name, and the header says so
  // in words, because a fake wallet that is not obviously fake is a way to lose real money.

  function devProvider(rpcUrl, startAt) {
    var accounts = [];
    var current = startAt || 0;

    return {
      isDev: true,
      accounts: function () { return accounts; },
      use: function (i) {
        current = i;
        state.account = accounts[current];
        emit();
      },
      request: async function (req) {
        if (req.method === "eth_requestAccounts" || req.method === "eth_accounts") {
          accounts = await Eth.rpc(rpcUrl, "eth_accounts", []);
          return [accounts[current]];
        }
        if (req.method === "eth_chainId") return Eth.rpc(rpcUrl, "eth_chainId", []);
        if (req.method === "eth_sendTransaction") {
          var tx = Object.assign({}, req.params[0]);
          tx.from = tx.from || accounts[current];
          return Eth.rpc(rpcUrl, "eth_sendTransaction", [tx]);
        }
        return Eth.rpc(rpcUrl, req.method, req.params || []);
      }
    };
  }

  // ------------------------------------------------------------------ connection

  function init(config) {
    cfg = config;
    if (cfg.devWallet) {
      provider = devProvider(cfg.chain.rpc, cfg.devAccount);
      state.kind = "dev";
    } else if (window.ethereum) {
      provider = window.ethereum;
      state.kind = "injected";
      provider.on("chainChanged", function (id) { state.chainId = Number(id); emit(); });
      provider.on("accountsChanged", function (a) { state.account = (a && a[0]) || null; emit(); });
    }
    return !!provider;
  }

  function available() {
    return !!provider;
  }

  async function connect() {
    if (!provider) throw new Error("No wallet was found in this browser.");
    var accounts = await provider.request({ method: "eth_requestAccounts" });
    state.account = accounts && accounts[0];
    state.chainId = Number(await provider.request({ method: "eth_chainId" }));
    emit();
    return state.account;
  }

  /** Picks up an authorisation already given, without asking for one.

      eth_accounts never prompts: it reports what the wallet has already agreed to. Without this,
      somebody who reloads the page, or opens a link straight to a deal, is told to connect a
      wallet that is already connected, and the screen behind that message is drawn empty.

      @returns the account, or null when there is nothing to restore. */
  async function restore() {
    if (!provider) return null;
    var accounts = await provider.request({ method: "eth_accounts" });
    if (!accounts || !accounts.length) return null;
    state.account = accounts[0];
    state.chainId = Number(await provider.request({ method: "eth_chainId" }));
    emit();
    return state.account;
  }

  /** @returns true when the wallet is on the chain the page is configured for. */
  function onRightChain() {
    return state.chainId === cfg.chain.id;
  }

  async function switchChain() {
    var hex = "0x" + cfg.chain.id.toString(16);
    try {
      await provider.request({ method: "wallet_switchEthereumChain", params: [{ chainId: hex }] });
    } catch (err) {
      // 4902 is "the wallet has never heard of this chain", which is ordinary on a young one.
      if (err && (err.code === 4902 || (err.data && err.data.originalError &&
                                        err.data.originalError.code === 4902))) {
        await provider.request({
          method: "wallet_addEthereumChain",
          params: [{
            chainId: hex,
            chainName: cfg.chain.name,
            nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
            rpcUrls: [cfg.chain.rpc],
            blockExplorerUrls: cfg.chain.explorer ? [cfg.chain.explorer] : []
          }]
        });
      } else {
        throw err;
      }
    }
    state.chainId = Number(await provider.request({ method: "eth_chainId" }));
    emit();
  }

  // ------------------------------------------------------------------ sending

  /** Asks the chain what this call would do, so a refusal is named before it is paid for. */
  async function preflight(to, data) {
    await Eth.rpc(cfg.chain.rpc, "eth_call", [{ from: state.account, to: to, data: data }, "latest"]);
  }

  async function send(to, data) {
    if (!state.account) await connect();
    if (!onRightChain()) await switchChain();
    await preflight(to, data);
    return provider.request({
      method: "eth_sendTransaction",
      params: [{ from: state.account, to: to, data: data }]
    });
  }

  /** Polls for the receipt. Blocks here are about 100 ms, so this is short and not worth a subscription. */
  async function wait(hash, timeoutMs) {
    var deadline = Date.now() + (timeoutMs || 60000);
    while (Date.now() < deadline) {
      var r = await Eth.rpc(cfg.chain.rpc, "eth_getTransactionReceipt", [hash]);
      if (r) {
        if (BigInt(r.status) === 0n) throw new Error("The transaction was mined and reverted.");
        return r;
      }
      await new Promise(function (ok) { setTimeout(ok, 400); });
    }
    throw new Error("The transaction has not been mined yet. It may still go through.");
  }

  return {
    init: init, available: available, connect: connect, restore: restore, on: on,
    onRightChain: onRightChain, switchChain: switchChain,
    send: send, wait: wait,
    state: state,
    provider: function () { return provider; }
  };
})();
