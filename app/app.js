/* Tenure app. No framework, no build step, no dependency: the same rule the contracts and the
   services follow, for the same reason.

   Three screens, which are the three positions a person can be in. Value: what is this position
   worth and what could it be offered for, answered by the API, needing no wallet. Market: what is
   on offer right now, read straight from the vault. You: what you are a party to, and what the
   vault is holding for you.

   Every number shown for a deal comes from the chain. The API is consulted for one thing only —
   what a position is worth and what it earns — because that is the one thing the chain does not
   say in a single call. */

(function () {
  "use strict";

  // ------------------------------------------------------------------ configuration

  var CFG = JSON.parse(JSON.stringify(window.TENURE));

  /* A development override, accepted only when this page is being served from the machine it is
     running on. Anywhere else a link could otherwise point the app at somebody else's RPC and
     somebody else's "vault", and the first thing that would do is ask for an approval. */
  var isLocal = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
  var params = new URLSearchParams(location.search);
  if (isLocal) {
    if (params.get("rpc")) CFG.chain.rpc = params.get("rpc");
    if (params.get("vault")) CFG.vault = params.get("vault");
    CFG.devWallet = params.get("wallet") === "dev";
  }

  var HAS_VAULT = /^0x[0-9a-fA-F]{40}$/.test(CFG.vault || "");
  var DEC = CFG.usdgDecimals;

  // ------------------------------------------------------------------ small helpers

  function $(id) { return document.getElementById(id); }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  function say(text, kind) {
    var m = $("msg");
    m.textContent = text;
    m.className = "msg show " + (kind || "info");
    m.scrollIntoView({ block: "nearest" });
  }

  function quiet() { $("msg").className = "msg"; }

  function short(a) { return a ? a.slice(0, 6) + "…" + a.slice(-4) : "—"; }

  /** "1 deal has" / "4 deals have". A page that says "1 deals" was written by nobody. */
  function count(n, noun) {
    return n + " " + noun + (n === 1 ? " has" : "s have");
  }

  function same(a, b) { return !!a && !!b && a.toLowerCase() === b.toLowerCase(); }

  function usdg(units, places) { return Eth.fromUnits(units, DEC, places === undefined ? 2 : places); }

  function duration(seconds) {
    var s = Math.abs(Math.round(Number(seconds)));
    if (s >= 86400) return Math.round(s / 86400) + (Math.round(s / 86400) === 1 ? " day" : " days");
    if (s >= 3600) return Math.round(s / 3600) + " h";
    if (s >= 60) return Math.round(s / 60) + " min";
    return s + " s";
  }

  /** "in 6 days" / "5 h ago", which is what somebody reading a deadline actually wants. */
  function when(unixSeconds) {
    var delta = Number(unixSeconds) - Math.floor(Date.now() / 1000);
    return delta >= 0 ? "in " + duration(delta) : duration(delta) + " ago";
  }

  function row(parent, k, v, accent) {
    var r = el("div", "row");
    r.appendChild(el("span", "k", k));
    r.appendChild(el("span", "v" + (accent ? " am" : ""), v));
    parent.appendChild(r);
    return r;
  }

  function tile(parent, k, v, u, accent) {
    var t = el("div", "tile" + (accent ? " am" : ""));
    t.appendChild(el("div", "k", k));
    t.appendChild(el("div", "v", v));
    if (u) t.appendChild(el("div", "u", u));
    parent.appendChild(t);
  }

  function term(parent, k, v) {
    var d = el("div");
    d.appendChild(el("div", "k", k));
    d.appendChild(el("div", "v", v));
    parent.appendChild(d);
  }

  /** The API writes reasons as fragments, lower case and unpunctuated. Pages are not logs. */
  function sentence(text) {
    var t = String(text || "").trim();
    if (!t) return "";
    t = t.charAt(0).toUpperCase() + t.slice(1);
    return /[.!?]$/.test(t) ? t : t + ".";
  }

  // ------------------------------------------------------------------ reading the chain

  function call(to, data) {
    return Eth.rpc(CFG.chain.rpc, "eth_call", [{ to: to, data: data }, "latest"]);
  }

  async function vault(sig, args) {
    return Eth.returns(sig, await call(CFG.vault, Eth.calldata(sig, args || [])));
  }

  async function readDeal(id) {
    var d = Eth.struct("Deal", await call(CFG.vault, Eth.calldata("deal(uint256)", [id])));
    d.id = id;
    d.stateName = window.TENURE_ABI.state[Number(d.state)];
    return d;
  }

  /** Token calls are not on the vault, so their selectors come from the hand-checked table. */
  function tokenData(sig, types, args) {
    var sel = window.TENURE_ABI.token[sig];
    if (!sel) throw new Error("no selector for " + sig);
    return sel + types.map(function (t, i) { return Eth.encodeOne(t, args[i]); }).join("");
  }

  async function usdgAllowance(owner) {
    var d = tokenData("allowance(address,address)", ["address", "address"], [owner, CFG.vault]);
    return BigInt(await call(CFG.usdg, d));
  }

  async function usdgBalance(owner) {
    return BigInt(await call(CFG.usdg, tokenData("balanceOf(address)", ["address"], [owner])));
  }

  async function positionApproved(tokenId) {
    var d = tokenData("getApproved(uint256)", ["uint256"], [tokenId]);
    return Eth.decodeOne("address", Eth.words(await call(CFG.posm, d))[0]);
  }

  async function positionOwner(tokenId) {
    var d = tokenData("ownerOf(uint256)", ["uint256"], [tokenId]);
    return Eth.decodeOne("address", Eth.words(await call(CFG.posm, d))[0]);
  }

  /** Reads deals 1..dealCount. The vault numbers them from one and never deletes one, so this is
      the whole history and it is enumerable without an indexer. Chunked so a slow node is not hit
      with four hundred calls at once. */
  async function allDeals() {
    var n = Number(await vault("dealCount()"));
    var out = [];
    for (var start = 1; start <= n; start += 12) {
      var batch = [];
      for (var i = start; i < start + 12 && i <= n; i++) batch.push(readDeal(i));
      out = out.concat(await Promise.all(batch));
    }
    return out;
  }

  // ------------------------------------------------------------------ writing

  var busy = false;

  /** One place where every write happens, so every write reports the same way. */
  async function act(button, label, to, data, after) {
    if (busy) return;
    busy = true;
    var original = button.textContent;
    button.disabled = true;
    button.textContent = label;
    quiet();
    try {
      var hash = await Wallet.send(to, data);
      button.textContent = "waiting for the block…";
      await Wallet.wait(hash);
      say(sentence(label.replace(/…$/, "") + " done"), "ok");
      if (after) await after();
    } catch (err) {
      var text = Eth.explain(err);
      if (text) say(text, "err");
    } finally {
      busy = false;
      button.disabled = false;
      button.textContent = original;
    }
  }

  /** Approvals are for the exact amount needed. An unlimited approval is convenient once and then
      permanent, and this vault is not special enough to deserve one. */
  async function ensureUsdgAllowance(button, amount) {
    var have = await usdgAllowance(Wallet.state.account);
    if (have >= amount) return true;
    var data = tokenData("approve(address,uint256)", ["address", "uint256"], [CFG.vault, amount]);
    var done = false;
    await act(button, "approving " + usdg(amount) + " USDG…", CFG.usdg, data, function () { done = true; });
    return done;
  }

  // ------------------------------------------------------------------ view: value

  var lastQuote = null;

  async function lookup() {
    var id = $("tokenId").value.trim();
    if (!/^[0-9]{1,78}$/.test(id)) {
      say("A position id is a number. Try 2908273.", "err");
      return;
    }
    var btn = $("lookup");
    btn.disabled = true;
    btn.textContent = "Reading the chain…";
    quiet();
    $("result").textContent = "";

    try {
      var res = await fetch(CFG.api + "/v1/position/" + id + "/quote");
      var data = await res.json();
      if (res.status === 404) return say("No position with that id on this chain.", "err");
      if (res.status === 402) {
        return say("The API is asking to be paid for this request. The public deployment runs " +
                   "free, so this is a different instance.", "err");
      }
      if (!res.ok) return say(data.message || data.error || "The chain could not be read right now.", "err");
      lastQuote = data;
      renderQuote(data);
      history.replaceState(null, "", "?id=" + id + (location.hash || ""));
    } catch (err) {
      say("Could not reach the valuation API: " + (err && err.message ? err.message : err), "err");
    } finally {
      btn.disabled = false;
      btn.textContent = "Value it";
    }
  }

  function renderQuote(d) {
    var out = $("result");
    out.textContent = "";

    var pool = d.pool || {}, pos = d.position || {}, value = d.valueUSDG;
    var rate = d.feeRate || {}, quote = d.quote || {};

    // ---- the position
    var p1 = el("div", "panel");
    p1.appendChild(el("h2", null, "Position " + d.tokenId));

    var pills = el("div");
    pills.style.marginBottom = "16px";
    // An emptied position is still "in range": its interval contains the price, it just holds
    // nothing. A green badge on that says the opposite of what matters.
    var empty = pos.liquidity === "0";
    var st = empty ? ["no", "empty"] : pos.inRange ? ["ok", "in range"] : ["no", "out of range"];
    pills.appendChild(el("span", "pill " + st[0], st[1]));
    if (pos.hasSubscriber) pills.appendChild(el("span", "pill no", "has a subscriber"));
    p1.appendChild(pills);

    var rows = el("div", "rows");
    row(rows, "Pair", (pool.token0 && pool.token0.symbol) + " / " + (pool.token1 && pool.token1.symbol));
    var owner = row(rows, "Owner", pos.owner || d.owner || "—");
    // Asked of the chain this page is configured for. The API answers about the chain it is
    // configured for, and the listing button acts on this one, so this is the row that has to be
    // right. They agree in production and they do not agree against a fork.
    positionOwner(d.tokenId).then(function (a) {
      owner.querySelector(".v").textContent = a;
    }, function () { /* a node that will not answer leaves the API's reading in place */ });
    row(rows, "Range", pos.tickLower + " → " + pos.tickUpper);
    row(rows, "Liquidity", pos.liquidity);
    if (value) {
      row(rows, "Held", Number(value.principal).toFixed(2) + " USDG");
      row(rows, "Uncollected fees", Number(value.fees).toFixed(2) + " USDG");
      row(rows, "Market value", Number(value.total).toFixed(2) + " USDG", true);
    } else if (d.valueNote) {
      row(rows, "Value", d.valueNote);
    }
    p1.appendChild(rows);
    out.appendChild(p1);

    // ---- what it earns
    var p2 = el("div", "panel");
    p2.appendChild(el("h2", null, "What the range earns"));
    if (rate.available) {
      var r2 = el("div", "rows");
      row(r2, "Fees per day", Number(rate.feesPerDayUSDG).toFixed(2) + " USDG", true);
      row(r2, "Fee APR", rate.feeAprPercent ? rate.feeAprPercent.toFixed(2) + " %" : "—");
      row(r2, "Measured over", duration(rate.windowSeconds) + " of chain history");
      row(r2, "Source", rate.source + (rate.lowConfidence ? " · low confidence" : ""));
      p2.appendChild(r2);
      if (rate.plausible === false) {
        p2.appendChild(el("p", "note", "The pool's fee counter has wrapped around, so these " +
          "figures are not usable. No terms are proposed from them."));
      }
    } else {
      p2.appendChild(el("p", "note", sentence(rate.reason || "No fee rate could be measured")));
    }
    out.appendChild(p2);

    // ---- the terms
    var p3 = el("div", "panel");
    p3.appendChild(el("h2", null, "Indicative terms"));
    if (quote.available) {
      var tiles = el("div", "tiles");
      tile(tiles, "SALE PRICE", Number(quote.suggestedSalePriceUSDG).toFixed(2), "USDG", true);
      tile(tiles, "BUYBACK", Number(quote.suggestedBuybackPriceUSDG).toFixed(2), "USDG", true);
      tile(tiles, "RENT · " + quote.termDays + " DAYS", Number(quote.suggestedRentUSDG).toFixed(2), "USDG");
      p3.appendChild(tiles);

      var note = "The buyback equals the sale price. The contract refuses any listing where it is " +
        "higher, so the financier is paid for the use of the asset and never for the passage of time.";
      if (quote.feeRateLowConfidence) note += " The rent rests on a narrow window of history; price it accordingly.";
      var pn = el("p", "note", note);
      pn.style.marginTop = "16px";
      p3.appendChild(pn);
    } else {
      p3.appendChild(el("p", "note", sentence(quote.reason || "No terms could be derived") +
        " Offering it anyway would produce a listing the vault rejects."));
    }
    out.appendChild(p3);

    // ---- offering it
    out.appendChild(listingPanel(d));
  }

  /** The seller's side. Shown only when there is a vault to list into and the terms are derivable;
      filled in from the quote, and every field is theirs to overwrite. */
  function listingPanel(d) {
    var p = el("div", "panel");
    p.appendChild(el("h2", null, "Offer it"));

    if (!HAS_VAULT) {
      p.appendChild(el("p", "note", "Listing needs the vault, and no contract is deployed on any " +
        "chain yet. When one is, this is where the terms above become an offer somebody can fund."));
      return p;
    }
    var quote = d.quote || {};
    if (!quote.available) {
      p.appendChild(el("p", "note", "No terms could be derived for this position, so there is " +
        "nothing to offer. The vault would refuse the listing."));
      return p;
    }

    var form = el("div", "fields");
    var inputs = {};
    function field(key, label, value, hint) {
      var f = el("div", "field");
      var id = "f-" + key;
      var l = el("label", null, label);
      l.setAttribute("for", id);
      var i = el("input");
      i.type = "text";
      i.id = id;
      i.value = value;
      i.setAttribute("inputmode", "decimal");
      f.appendChild(l);
      f.appendChild(i);
      if (hint) f.appendChild(el("span", "hint", hint));
      form.appendChild(f);
      inputs[key] = i;
    }

    field("price", "Sale price · USDG", Number(quote.suggestedSalePriceUSDG).toFixed(2),
          "What the financier pays you now.");
    field("buyback", "Buyback · USDG", Number(quote.suggestedBuybackPriceUSDG).toFixed(2),
          "Never above the sale price.");
    field("rent", "Rent for the term · USDG", Number(quote.suggestedRentUSDG).toFixed(2),
          "Prepaid out of your own proceeds.");
    field("termDays", "Term · days", String(quote.termDays || 7), "Between 1 and 30.");
    field("graceHours", "Grace · hours", "48", "Between 24 and 168.");
    field("listingDays", "Offer open for · days", "7", "Up to 30.");
    p.appendChild(form);

    var adv = el("details");
    adv.appendChild(el("summary", null, "Builder code and freeze handling"));
    var form2 = el("div", "fields");
    var keep = form;
    form = form2;
    field("builder", "Builder · address", "0x0000000000000000000000000000000000000000",
          "Whoever brought you this deal, paid out of your proceeds.");
    field("builderFee", "Builder fee · USDG", "0", "At most a hundredth of the sale price.");
    field("maxFrozenBps", "Frozen time credited · bps", "5000",
          "Ceiling on how much of the term can stop the rent. At most 5000.");
    field("freezeProbe", "Freeze probe", "0", "0 never asks the pair whether it is frozen, 1 calls paused().");
    form = keep;
    adv.appendChild(form2);
    p.appendChild(adv);

    var bar = el("div", "bar");
    var go = el("button", "primary", "List this position");
    bar.appendChild(go);
    p.appendChild(bar);

    var why = el("p", "note");
    p.appendChild(why);

    /** The contract is the authority on every one of these bounds. Checking them here only means
        somebody learns they got it wrong before they pay for a block, not instead of. */
    function read() {
      var t = {
        price: Eth.toUnits(inputs.price.value.trim(), DEC),
        rent: Eth.toUnits(inputs.rent.value.trim(), DEC),
        buybackPrice: Eth.toUnits(inputs.buyback.value.trim(), DEC),
        term: BigInt(Math.round(Number(inputs.termDays.value) * 86400)),
        grace: BigInt(Math.round(Number(inputs.graceHours.value) * 3600)),
        listingDuration: BigInt(Math.round(Number(inputs.listingDays.value) * 86400)),
        maxFrozenBps: BigInt(inputs.maxFrozenBps.value.trim()),
        freezeProbe: BigInt(inputs.freezeProbe.value.trim()),
        builder: inputs.builder.value.trim(),
        builderFee: Eth.toUnits(inputs.builderFee.value.trim(), DEC)
      };
      var bad = null;
      if (t.price === 0n || t.rent === 0n || t.buybackPrice === 0n) bad = "A price, a rent and a buyback must all be above zero.";
      else if (t.buybackPrice > t.price) bad = "The buyback cannot be above the sale price. The vault refuses it.";
      else if (t.rent + t.builderFee >= t.price) bad = "The rent and the builder fee together have to leave you something: they must be below the sale price.";
      else if (t.term < 86400n || t.term > 2592000n) bad = "The term has to be between 1 and 30 days.";
      else if (t.grace < 86400n || t.grace > 604800n) bad = "The grace window has to be between 24 and 168 hours.";
      else if (t.listingDuration === 0n || t.listingDuration > 2592000n) bad = "The offer can stay open for up to 30 days.";
      else if (t.maxFrozenBps > 5000n) bad = "At most half a term can be credited as frozen: 5000 bps.";
      else if (t.freezeProbe > 1n) bad = "The freeze probe is 0 or 1.";
      else if (t.builderFee > t.price / 100n) bad = "A builder fee is at most a hundredth of the sale price.";
      return { t: t, bad: bad };
    }

    go.addEventListener("click", async function () {
      var parsed;
      try {
        parsed = read();
      } catch (err) {
        return say(err.message, "err");
      }
      if (parsed.bad) return say(parsed.bad, "err");

      if (!Wallet.state.account) {
        try { await Wallet.connect(); } catch (err) { return say(Eth.explain(err) || "", "err"); }
      }
      var owner = await positionOwner(d.tokenId);
      if (!same(owner, Wallet.state.account)) {
        return say("This position belongs to " + short(owner) + ", and you are connected as " +
                   short(Wallet.state.account) + ". Only its owner can offer it.", "err");
      }

      // The vault takes delivery of the NFT inside list(), so it has to be approved first.
      var approved = await positionApproved(d.tokenId);
      if (!same(approved, CFG.vault)) {
        var okd = false;
        var data = tokenData("approve(address,uint256)", ["address", "uint256"], [CFG.vault, d.tokenId]);
        await act(go, "approving the position…", CFG.posm, data, function () { okd = true; });
        if (!okd) return;
      }

      var fields = window.TENURE_ABI.struct.Terms.map(function (f) { return parsed.t[f[0]]; });
      var cd = Eth.calldata("list(uint256,(uint128,uint128,uint128,uint32,uint32,uint32,uint16,uint8,address,uint128))",
                            [d.tokenId, fields]);
      await act(go, "listing…", CFG.vault, cd, async function () {
        var n = await vault("dealCount()");
        say("Listed as deal " + n + ". It is on the market until somebody funds it or the offer expires.", "ok");
        go.disabled = true;
      });
    });

    why.textContent = "Listing hands the position to the vault. You keep collecting its fees for " +
      "the whole term, and you can buy it back at any time until the grace window closes.";
    return p;
  }

  // ------------------------------------------------------------------ view: market

  async function renderMarket() {
    var out = $("market");
    out.textContent = "";
    if (!HAS_VAULT) return out.appendChild(noVault());

    out.appendChild(el("p", "note", "Reading the vault…"));
    var deals;
    try {
      deals = await allDeals();
    } catch (err) {
      out.textContent = "";
      return out.appendChild(el("p", "note", "The chain could not be read: " + (err.message || err)));
    }
    var now = Math.floor(Date.now() / 1000);
    var open = deals.filter(function (d) { return Number(d.state) === 1 && Number(d.listingExpiry) > now; });

    out.textContent = "";
    if (!open.length) {
      var p = el("div", "panel");
      p.appendChild(el("p", "note", deals.length
        ? "Nothing is on offer right now. " + count(deals.length, "deal") + " been listed here."
        : "Nothing has been listed on this vault yet."));
      return out.appendChild(p);
    }
    open.forEach(function (d) { out.appendChild(dealCard(d, "market")); });
  }

  function noVault() {
    var p = el("div", "panel");
    p.appendChild(el("p", "note", "No LeaseVault is deployed on any chain, so there is no market to " +
      "read. The valuation screen works without one."));
    return p;
  }

  // ------------------------------------------------------------------ view: you

  async function renderYou() {
    var out = $("you");
    out.textContent = "";
    if (!HAS_VAULT) return out.appendChild(noVault());

    var me = Wallet.state.account;
    if (!me) {
      var p = el("div", "panel");
      p.appendChild(el("p", "note", "Connect a wallet to see the deals you are a party to."));
      var b = el("button", "ghost small", "Connect wallet");
      b.addEventListener("click", doConnect);
      p.appendChild(b);
      return out.appendChild(p);
    }

    out.appendChild(el("p", "note", "Reading the vault…"));
    var deals, owed, held;
    try {
      deals = await allDeals();
      owed = await vault("balances(address)", [me]);
      held = await usdgBalance(me);
    } catch (err) {
      out.textContent = "";
      return out.appendChild(el("p", "note", "The chain could not be read: " + (err.message || err)));
    }
    var mine = deals.filter(function (d) { return same(d.seller, me) || same(d.financier, me); });

    out.textContent = "";

    var top = el("div", "panel");
    top.appendChild(el("h2", null, "Held for you"));
    var rows = el("div", "rows");
    row(rows, "Withdrawable from the vault", usdg(owed) + " USDG", owed > 0n);
    row(rows, "In your wallet", usdg(held) + " USDG");
    top.appendChild(rows);
    if (owed > 0n) {
      var bar = el("div", "bar");
      bar.style.marginTop = "16px";
      bar.style.marginBottom = "0";
      var w = el("button", "primary", "Withdraw " + usdg(owed) + " USDG");
      w.addEventListener("click", function () {
        act(w, "withdrawing…", CFG.vault, Eth.calldata("withdrawUSDG()", []), renderYou);
      });
      bar.appendChild(w);
      top.appendChild(bar);
    }
    out.appendChild(top);

    // A position the vault is holding for you: after a cancel, a buyback, or a release.
    var tokenIds = [];
    mine.forEach(function (d) {
      if (tokenIds.indexOf(String(d.tokenId)) < 0) tokenIds.push(String(d.tokenId));
    });
    var waiting = await Promise.all(tokenIds.map(async function (tokenId) {
      var claimant = Eth.returns("positionOwed(uint256)",
        await call(CFG.vault, Eth.calldata("positionOwed(uint256)", [tokenId])));
      return same(claimant, me) ? tokenId : null;
    }));
    waiting.filter(Boolean).forEach(function (tokenId) {
      var p = el("div", "panel");
      p.appendChild(el("h2", null, "Position " + tokenId + " is waiting for you"));
      p.appendChild(el("p", "note", "The vault is holding it. Nothing expires; take it when you like."));
      var bar = el("div", "bar");
      bar.style.marginTop = "16px";
      bar.style.marginBottom = "0";
      var b = el("button", "primary", "Withdraw the position");
      b.addEventListener("click", function () {
        act(b, "withdrawing…", CFG.vault, Eth.calldata("withdrawPosition(uint256)", [tokenId]), renderYou);
      });
      bar.appendChild(b);
      p.appendChild(bar);
      out.appendChild(p);
    });

    if (!mine.length) {
      var none = el("div", "panel");
      none.appendChild(el("p", "note", "You are not a party to any deal on this vault."));
      out.appendChild(none);
      return;
    }
    mine.forEach(function (d) { out.appendChild(dealCard(d, "you")); });
  }

  // ------------------------------------------------------------------ a deal, and what you can do to it

  function dealCard(d, where) {
    var me = Wallet.state.account;
    var isSeller = same(d.seller, me);
    var isFinancier = same(d.financier, me);
    var now = Math.floor(Date.now() / 1000);

    var card = el("div", "deal");

    var head = el("div", "head");
    head.appendChild(el("h3", null, "Deal " + d.id));
    head.appendChild(el("span", "note", "position " + d.tokenId));
    head.appendChild(el("span", "spacer"));
    var st = Number(d.state);
    var look = st === 1 ? "wait" : st === 2 ? "ok" : st === 3 ? "ok" : "no";
    head.appendChild(el("span", "pill " + look, d.stateName.replace(/([a-z])([A-Z])/g, "$1 $2")));
    if (isSeller) head.appendChild(el("span", "pill ok", "you are the lessee"));
    if (isFinancier) head.appendChild(el("span", "pill ok", "you are the financier"));
    card.appendChild(head);

    var terms = el("div", "terms");
    term(terms, "SALE PRICE", usdg(d.price) + " USDG");
    term(terms, "BUYBACK", usdg(d.buybackPrice) + " USDG");
    term(terms, "RENT · " + duration(d.term), usdg(d.rent) + " USDG");
    if (st === 1) term(terms, "OFFER CLOSES", when(d.listingExpiry));
    else if (st === 2) term(terms, "LEASE ENDS", when(Number(d.fundedAt) + Number(d.term)));
    else term(terms, "GRACE", duration(d.grace));
    card.appendChild(terms);

    if (st === 2) {
      var rows = el("div", "rows");
      row(rows, "Buy-back window closes", when(Number(d.fundedAt) + Number(d.term) + Number(d.grace)));
      row(rows, "Rent already credited", usdg(d.rentClaimed) + " of " + usdg(d.rent) + " USDG");
      if (Number(d.pausedTotal) > 0 || Number(d.pausedSince) > 0) {
        row(rows, "Frozen time recorded", duration(d.pausedTotal));
      }
      card.appendChild(rows);
    }

    var acts = el("div", "acts");
    var any = false;

    function button(label, cls, fn) {
      var b = el("button", (cls || "ghost") + " small", label);
      b.addEventListener("click", function () { fn(b); });
      acts.appendChild(b);
      any = true;
      return b;
    }

    // ---- listed
    if (st === 1) {
      if (!isSeller) {
        button("Fund it · " + usdg(d.price) + " USDG", "primary", async function (b) {
          if (!Wallet.state.account) {
            try { await Wallet.connect(); } catch (err) { return say(Eth.explain(err) || "", "err"); }
          }
          var have = await usdgBalance(Wallet.state.account);
          if (have < d.price) {
            return say("Funding this needs " + usdg(d.price) + " USDG and you hold " + usdg(have) + ".", "err");
          }
          if (!(await ensureUsdgAllowance(b, d.price))) return;
          await act(b, "funding…", CFG.vault, Eth.calldata("fund(uint256)", [d.id]), refresh);
        });
      }
      if (isSeller) {
        button("Cancel the offer", "ghost", function (b) {
          act(b, "cancelling…", CFG.vault, Eth.calldata("cancel(uint256)", [d.id]), refresh);
        });
      }
    }

    // ---- active
    if (st === 2) {
      if (isSeller) {
        if (now <= Number(d.fundedAt) + Number(d.term)) {
          button("Collect the fees", "ghost", function (b) {
            act(b, "collecting…", CFG.vault, Eth.calldata("collectFees(uint256)", [d.id]), refresh);
          });
        }
        button("Buy it back · " + usdg(d.buybackPrice) + " USDG", "primary", async function (b) {
          var have = await usdgBalance(Wallet.state.account);
          if (have < d.buybackPrice) {
            return say("Buying it back needs " + usdg(d.buybackPrice) + " USDG and you hold " + usdg(have) + ".", "err");
          }
          if (!(await ensureUsdgAllowance(b, d.buybackPrice))) return;
          await act(b, "buying back…", CFG.vault, Eth.calldata("buyBack(uint256)", [d.id]), refresh);
        });
      }
      if (isFinancier) {
        button("Claim the rent so far", "ghost", function (b) {
          act(b, "claiming…", CFG.vault, Eth.calldata("claimRent(uint256)", [d.id]), refresh);
        });
        if (now >= Number(d.fundedAt) + Number(d.term) + Number(d.grace)) {
          button("Take delivery", "primary", function (b) {
            act(b, "releasing…", CFG.vault, Eth.calldata("release(uint256)", [d.id]), refresh);
          });
        }
      }
    }

    if (any) card.appendChild(acts);
    else if (where === "market" && st === 1 && isSeller) {
      card.appendChild(el("p", "note", "This is your own listing, and the vault refuses to let you fund it."));
    }
    return card;
  }

  // ------------------------------------------------------------------ routing

  var VIEWS = ["value", "market", "you"];

  function show(name) {
    if (VIEWS.indexOf(name) < 0) name = "value";
    VIEWS.forEach(function (v) {
      document.querySelector('[data-view="' + v + '"]').classList.toggle("hidden", v !== name);
    });
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (t) {
      if (t.dataset.go === name) t.setAttribute("aria-current", "page");
      else t.removeAttribute("aria-current");
    });
    quiet();
    if (name === "market") renderMarket();
    if (name === "you") renderYou();
  }

  function current() { return (location.hash || "#value").slice(1); }

  function refresh() {
    var v = current();
    if (v === "market") return renderMarket();
    if (v === "you") return renderYou();
  }

  // ------------------------------------------------------------------ wiring

  async function doConnect() {
    try {
      await Wallet.connect();
      if (!Wallet.onRightChain()) await Wallet.switchChain();
      quiet();
      refresh();
    } catch (err) {
      var text = Eth.explain(err);
      if (text) say(text, "err");
    }
  }

  function paintWallet(s) {
    var net = $("net"), connect = $("connect");
    if (!s.account) {
      net.textContent = "not connected";
      net.className = "net";
      connect.textContent = "Connect wallet";
      return;
    }
    connect.textContent = short(s.account);
    if (s.chainId === CFG.chain.id) {
      net.textContent = CFG.chain.name + " · " + CFG.chain.id;
      net.className = "net on";
    } else {
      net.textContent = "wrong network · switch to " + CFG.chain.id;
      net.className = "net off";
    }
  }

  function initDevBanner() {
    if (!CFG.devWallet) return;
    $("dev").classList.remove("hidden");
    $("dev-vault").textContent = CFG.vault || "none";
    var sel = $("dev-account");
    Wallet.connect().then(function () {
      Wallet.provider().accounts().forEach(function (a, i) {
        var o = el("option", null, (i === 0 ? "seller " : i === 1 ? "financier " : "account " + i + " ") + short(a));
        o.value = String(i);
        sel.appendChild(o);
      });
      sel.addEventListener("change", function () {
        Wallet.provider().use(Number(sel.value));
        refresh();
      });
    }).catch(function (err) {
      say("The development chain did not answer: " + (err.message || err), "err");
    });
  }

  $("connect").addEventListener("click", doConnect);
  $("lookup").addEventListener("click", lookup);
  $("tokenId").addEventListener("keydown", function (e) { if (e.key === "Enter") lookup(); });
  Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (t) {
    t.addEventListener("click", function () { location.hash = "#" + t.dataset.go; });
  });
  window.addEventListener("hashchange", function () { show(current()); });

  $("foot").textContent = HAS_VAULT
    ? "Vault " + CFG.vault + " on " + CFG.chain.name + ". "
    : "No contract is deployed yet, so nothing on this page can be listed or funded. ";

  Wallet.init(CFG);
  Wallet.on(paintWallet);
  initDevBanner();
  show(current());

  // A position id in the address bar makes a valuation shareable.
  var fromUrl = params.get("id");
  if (fromUrl) {
    $("tokenId").value = fromUrl;
    lookup();
  }
})();
