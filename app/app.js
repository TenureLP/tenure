/* Tenure app. No framework, no build step, no dependency: the same rule the rest of the project
   follows, for the same reason. Everything here either reads the valuation API or talks to the
   wallet through EIP-1193, and both are small enough to write out.

   Nothing on this page signs anything yet. No contract is deployed. */

(function () {
  "use strict";

  var API = window.TENURE_API || "https://api-production-9e87.up.railway.app";
  var CHAIN_ID = 4663;
  var CHAIN_HEX = "0x" + CHAIN_ID.toString(16);

  var $ = function (id) { return document.getElementById(id); };

  // ------------------------------------------------------------------ messages

  function say(text, kind) {
    var el = $("msg");
    el.textContent = text;
    el.className = "msg show " + (kind || "info");
  }

  function quiet() {
    $("msg").className = "msg";
  }

  // ------------------------------------------------------------------ wallet

  var account = null;

  function setNet(text, state) {
    var el = $("net");
    el.textContent = text;
    el.className = "net" + (state ? " " + state : "");
  }

  function short(addr) {
    return addr.slice(0, 6) + "…" + addr.slice(-4);
  }

  async function connect() {
    if (!window.ethereum) {
      say("No wallet was found in this browser. The page still values positions without one.", "err");
      return;
    }
    try {
      var accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
      account = accounts && accounts[0];
      var chain = await window.ethereum.request({ method: "eth_chainId" });
      onChain(chain);
      $("connect").textContent = short(account);
      quiet();
    } catch (err) {
      // 4001 is the user closing the prompt, which is not a failure worth shouting about.
      if (err && err.code === 4001) return;
      say("The wallet refused to connect: " + (err && err.message ? err.message : err), "err");
    }
  }

  function onChain(chainHex) {
    if (!account) return;
    if (String(chainHex).toLowerCase() === CHAIN_HEX) {
      setNet("Robinhood Chain · " + CHAIN_ID, "on");
    } else {
      setNet("wrong network · switch to " + CHAIN_ID, "off");
    }
  }

  if (window.ethereum) {
    window.ethereum.on("chainChanged", function (c) { onChain(c); });
    window.ethereum.on("accountsChanged", function (a) {
      account = a && a[0];
      $("connect").textContent = account ? short(account) : "Connect wallet";
      if (!account) setNet("not connected", "");
    });
  }

  // ------------------------------------------------------------------ formatting

  function usdg(n) {
    if (n === null || n === undefined) return "—";
    var abs = Math.abs(n);
    var digits = abs >= 1000 ? 2 : abs >= 1 ? 2 : abs >= 0.01 ? 4 : 6;
    return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  function hours(seconds) {
    if (!seconds) return "—";
    var h = seconds / 3600;
    return h >= 1 ? h.toFixed(1) + " h" : Math.round(seconds / 60) + " min";
  }

  /** The API writes reasons as fragments, lower case and unpunctuated. Pages are not logs. */
  function sentence(text) {
    var t = String(text).trim();
    if (!t) return "";
    t = t.charAt(0).toUpperCase() + t.slice(1);
    return /[.!?]$/.test(t) ? t : t + ".";
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function row(parent, key, value, accent) {
    var r = el("div", "row");
    r.appendChild(el("span", "k", key));
    r.appendChild(el("span", "v" + (accent ? " am" : ""), value));
    parent.appendChild(r);
    return r;
  }

  function tile(parent, key, value, unit, accent) {
    var t = el("div", "tile" + (accent ? " am" : ""));
    t.appendChild(el("div", "k", key));
    t.appendChild(el("div", "v", value));
    if (unit) t.appendChild(el("div", "u", unit));
    parent.appendChild(t);
  }

  // ------------------------------------------------------------------ lookup

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
    $("result").classList.add("hidden");

    try {
      var res = await fetch(API + "/v1/position/" + id + "/quote");
      var data = await res.json();

      if (res.status === 404) {
        say("No position with that id on this chain.", "err");
        return;
      }
      if (res.status === 402) {
        say("The API is asking to be paid for this request. The public deployment runs free, so " +
            "this is a different instance.", "err");
        return;
      }
      if (!res.ok) {
        say(data.message || data.error || "The chain could not be read right now.", "err");
        return;
      }
      render(data);
    } catch (err) {
      say("Could not reach the valuation API: " + (err && err.message ? err.message : err), "err");
    } finally {
      btn.disabled = false;
      btn.textContent = "Value it";
    }
  }

  function render(d) {
    var out = $("result");
    out.textContent = "";
    out.classList.remove("hidden");

    var pool = d.pool || {};
    var pos = d.position || {};
    var value = d.valueUSDG;
    var rate = d.feeRate || {};
    var quote = d.quote || {};

    // ---- the position
    var p1 = el("div", "panel");
    p1.appendChild(el("h2", null, "Position " + d.tokenId));

    var pills = el("div");
    pills.style.marginBottom = "16px";
    // An emptied position is still "in range": its interval contains the price, it just holds
    // nothing. A green badge on that says the opposite of what matters.
    var empty = pos.liquidity === "0";
    var state = empty ? ["no", "empty"] : pos.inRange ? ["ok", "in range"] : ["no", "out of range"];
    pills.appendChild(el("span", "pill " + state[0], state[1]));
    if (pos.hasSubscriber) {
      var sub = el("span", "pill no", "has a subscriber");
      sub.style.marginLeft = "8px";
      pills.appendChild(sub);
    }
    p1.appendChild(pills);

    var rows = el("div", "rows");
    row(rows, "Pair", (pool.token0 && pool.token0.symbol) + " / " + (pool.token1 && pool.token1.symbol));
    row(rows, "Owner", pos.owner || d.owner || "—");
    row(rows, "Range", pos.tickLower + " → " + pos.tickUpper);
    row(rows, "Liquidity", pos.liquidity);
    if (value) {
      row(rows, "Held", usdg(value.principal) + " USDG");
      row(rows, "Uncollected fees", usdg(value.fees) + " USDG");
      row(rows, "Market value", usdg(value.total) + " USDG", true);
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
      row(r2, "Fees per day", usdg(rate.feesPerDayUSDG) + " USDG", true);
      row(r2, "Fee APR", rate.feeAprPercent ? rate.feeAprPercent.toFixed(2) + " %" : "—");
      row(r2, "Measured over", hours(rate.windowSeconds) + " of chain history");
      row(r2, "Source", rate.source + (rate.lowConfidence ? " · low confidence" : ""));
      p2.appendChild(r2);
      if (rate.plausible === false) {
        p2.appendChild(el("p", "note",
          "The pool's fee counter has wrapped around, so these figures are not usable. " +
          "No terms are proposed from them."));
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
      tile(tiles, "SALE PRICE", usdg(quote.suggestedSalePriceUSDG), "USDG", true);
      tile(tiles, "BUYBACK", usdg(quote.suggestedBuybackPriceUSDG), "USDG", true);
      tile(tiles, "RENT · " + quote.termDays + " DAYS", usdg(quote.suggestedRentUSDG), "USDG");
      p3.appendChild(tiles);

      var note = "The buyback equals the sale price. The contract refuses any listing where it is " +
        "higher, so the financier is paid for the use of the asset and never for the passage of time.";
      if (quote.feeRateLowConfidence) {
        note += " The rent rests on a narrow window of history; price it accordingly.";
      }
      var pn = el("p", "note", note);
      pn.style.marginTop = "16px";
      p3.appendChild(pn);
    } else {
      p3.appendChild(el("p", "note", sentence(quote.reason || "No terms could be derived") +
        " Offering it anyway would produce a listing the vault rejects."));
    }
    out.appendChild(p3);

    // ---- what cannot happen yet
    var p4 = el("div", "panel");
    p4.appendChild(el("h2", null, "Next"));
    var soon = el("p", "note",
      "Listing this position needs the vault, and no contract is deployed on any chain yet. " +
      "When one is, this is where the terms above become an offer somebody can fund.");
    p4.appendChild(soon);
    out.appendChild(p4);
  }

  // ------------------------------------------------------------------ wiring

  $("connect").addEventListener("click", connect);
  $("lookup").addEventListener("click", lookup);
  $("tokenId").addEventListener("keydown", function (e) {
    if (e.key === "Enter") lookup();
  });

  // A position id in the address bar makes a valuation shareable.
  var fromUrl = new URLSearchParams(location.search).get("id");
  if (fromUrl) {
    $("tokenId").value = fromUrl;
    lookup();
  }
})();
