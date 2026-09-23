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

  var params = new URLSearchParams(location.search);
  var isLocal = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
  // A chain the reader chose -- in the url they opened, or from the selector -- is kept. One the
  // page only followed because a wallet sat on it is not, so the next wallet switch is followed too.
  var pinned = !!params.get("chain");

  var CFG, HAS_VAULT, TESTNET, HAS_FAUCET, DEC;

  /* Flattens one chain's entry into the shape the rest of this file reads. Everything below asks
     CFG for an address or an rpc and does not care which chain it came from, which is what keeps
     chain selection to this one function. */
  function useChain(id) {
    var chain = window.TENURE.chains[String(id)];
    if (!chain) return false;
    CFG = JSON.parse(JSON.stringify(chain));
    CFG.chain = { id: Number(id), name: chain.name, rpc: chain.rpc, explorer: chain.explorer };

    /* A development override, accepted only when this page is being served from the machine it is
       running on. Anywhere else a link could otherwise point the app at somebody else's RPC and
       somebody else's "vault", and the first thing that would do is ask for an approval. */
    if (isLocal) {
      if (params.get("rpc")) CFG.chain.rpc = params.get("rpc");
      if (params.get("vault")) CFG.vault = params.get("vault");
      if (params.get("usdg")) CFG.usdg = params.get("usdg");
      if (params.get("api")) CFG.api = params.get("api");
      if (params.get("faucet")) CFG.faucet = params.get("faucet");
      CFG.devWallet = params.get("wallet") === "dev";
      // Which development account to act as. Two windows side by side, one the seller and one
      // the financier, is how this flow is actually watched.
      CFG.devAccount = Math.max(0, Math.floor(Number(params.get("as")) || 0));
    }

    HAS_VAULT = /^0x[0-9a-fA-F]{40}$/.test(CFG.vault || "")
      && /^0x[0-9a-fA-F]{40}$/.test(CFG.usdg || "");
    // The quests and the faucet are test-network things. Mainnet is refused by id as well as by
    // configuration, for the reason the tUSDG button is.
    TESTNET = !!CFG.testToken && CFG.chain.id !== 4663;
    HAS_FAUCET = TESTNET && /^0x[0-9a-fA-F]{40}$/.test(CFG.faucet || "");
    DEC = CFG.usdgDecimals;
    return true;
  }

  function configuredChains() {
    return Object.keys(window.TENURE.chains).map(Number);
  }

  // A chain named in the url wins; otherwise the default. A connected wallet can move it later,
  // which is handled once the wallet has answered rather than guessed at here.
  useChain(Number(params.get("chain")) || window.TENURE.defaultChain)
    || useChain(window.TENURE.defaultChain);

  // ------------------------------------------------------------------ small helpers

  function $(id) { return document.getElementById(id); }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  /* A transaction reports itself in the corner, the way a wallet does, and stacks. The banner this
     replaces sat above the page and pushed whatever button the reader had just aimed at. */
  var TOAST_ICON = { ok: "check", err: "no-fee", info: "spark" };

  function say(text, kind, link) {
    kind = kind || "info";
    var host = $("toasts");
    var t = el("div", "toast " + kind);
    var icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icon.setAttribute("class", "ico");
    var use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#i-" + (TOAST_ICON[kind] || "spark"));
    icon.appendChild(use);
    t.appendChild(icon);

    var body = el("div");
    body.appendChild(el("p", null, text));
    if (link) {
      var a = el("a", null, link.label);
      a.href = link.href;
      a.target = "_blank";
      a.rel = "noopener";
      body.appendChild(a);
    }
    t.appendChild(body);

    var close = el("button", null, "\u00d7");
    close.type = "button";
    close.setAttribute("aria-label", "Dismiss");
    close.addEventListener("click", function () { drop(t); });
    t.appendChild(close);

    host.appendChild(t);
    while (host.children.length > 3) drop(host.firstElementChild, true);
    // An error is read, not glanced at, so it stays about twice as long.
    setTimeout(function () { drop(t); }, kind === "err" ? 14000 : 8000);
    return t;
  }

  function drop(t, now) {
    if (!t || !t.parentNode) return;
    if (now) return t.remove();
    t.classList.add("leaving");
    setTimeout(function () { t.remove(); }, 220);
  }

  /** Where a transaction can be checked by somebody who does not trust this page. Not on a fork:
      the explorer knows nothing about it and the link would be a dead end dressed as proof. */
  function txLink(hash) {
    if (!CFG.chain.explorer || CFG.devWallet || (isLocal && params.get("rpc"))) return null;
    return { href: CFG.chain.explorer.replace(/\/$/, "") + "/tx/" + hash, label: "View it on the explorer." };
  }

  function quiet() {
    Array.prototype.forEach.call($("toasts").children, function (t) { drop(t, true); });
  }

  function short(a) { return a ? a.slice(0, 6) + "…" + a.slice(-4) : "—"; }

  /** An explorer link for an address, shortened, with the whole address on hover. Plain text on a
      fork, where the explorer has never heard of anything. */
  function addr(a) {
    var usable = CFG.chain.explorer && !CFG.devWallet && !(isLocal && params.get("rpc"));
    var node = el(usable ? "a" : "span", null, HAS_VAULT && same(a, CFG.vault) ? "the vault" : short(a));
    node.title = a;
    if (usable) {
      node.href = CFG.chain.explorer.replace(/\/$/, "") + "/address/" + a;
      node.target = "_blank";
      node.rel = "noopener";
    }
    return node;
  }

  function rowNode(parent, k, node) {
    var r = row(parent, k, "");
    r.querySelector(".v").appendChild(node);
    return r;
  }

  /** The shape of the answer, drawn before it arrives, so nothing jumps when it does. `text` is
      what a screen reader is told, and printed small above the shape for everybody else. */
  function loading(text, figs) {
    var p = el("div", "sk-sheet");
    p.setAttribute("aria-busy", "true");
    p.setAttribute("aria-label", text);
    p.appendChild(el("p", "caption", text + "…"));
    p.appendChild(el("div", "sk h w40"));
    var grid = el("div", "sk-figs");
    for (var i = 0; i < (figs || 4); i++) {
      var col = el("div");
      col.appendChild(el("div", "sk w60"));
      col.appendChild(el("div", "sk t"));
      grid.appendChild(col);
    }
    p.appendChild(grid);
    p.appendChild(el("div", "sk w25"));
    return p;
  }

  // ------------------------------------------------------------------ the parts of a sheet

  var SVG = "http://www.w3.org/2000/svg";

  function svgEl(tag, attrs) {
    var e = document.createElementNS(SVG, tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    return e;
  }

  /** A document on the page: a band of references across the top, then a body to write in.
      Both looks draw from this; the corner marks only show at night. */
  function sheet(band, right) {
    var s = el("article", "sheet");
    ["tl", "tr", "bl", "br"].forEach(function (c) { s.appendChild(el("i", "reg " + c)); });
    var b = el("div", "band");
    band.filter(Boolean).forEach(function (x) { b.appendChild(typeof x === "string" ? el("span", null, x) : x); });
    if (right) {
      var r = typeof right === "string" ? el("span", null, right) : right;
      r.classList.add("r");
      b.appendChild(r);
    }
    s.appendChild(b);
    var body = el("div", "body");
    s.appendChild(body);
    return { node: s, body: body, band: b };
  }

  /** "Position No. 3093793", with the number set apart from its label. */
  function ref(label, value) {
    var s = el("span", null, label + " ");
    s.appendChild(el("b", null, String(value)));
    return s;
  }

  /** "ETH / USDG" with the stroke between them set back. */
  function pairHeading(a, b) {
    var h = el("h2", null, a + " ");
    h.appendChild(el("span", null, "/"));
    h.appendChild(document.createTextNode(" " + b));
    return h;
  }

  /** A sheet's heading, the line under it, and its stamps: [kind, text] each, kind being one of
      "", "bad", "wait", "flat". */
  function titleBlock(parent, heading, sub, stamps) {
    var t = el("div", "title");
    var left = el("div");
    left.appendChild(typeof heading === "string" ? el("h2", null, heading) : heading);
    if (sub) left.appendChild(el("p", "sub", sub));
    t.appendChild(left);
    if (stamps && stamps.length) {
      var st = el("div", "stamps");
      stamps.forEach(function (s) { st.appendChild(el("span", "stamp " + (s[0] || ""), s[1])); });
      t.appendChild(st);
    }
    parent.appendChild(t);
    return t;
  }

  /** One small figure inside a sheet: a label, the number, its unit, and a line under it. */
  function fig(parent, k, v, unit, accent, sub) {
    var f = el("div", "fig" + (accent ? " am" : ""));
    f.appendChild(el("p", "k", k));
    var val = el("p", "v");
    val.appendChild(el("span", "n", v));
    if (unit && v !== "—") val.appendChild(el("small", null, unit));
    f.appendChild(val);
    if (sub) f.appendChild(el("p", "u", sub));
    parent.appendChild(f);
  }

  /** A quantity of a token for reading: "0.9043", "6,625.00". The chain's eighteen places are
      what it stores, not what anybody reads. */
  function fmtAmount(x) {
    var n = Number(x);
    if (!isFinite(n)) return String(x);
    if (n === 0) return "0";
    return fmtPrice(n);
  }

  /** What the chain says about a position, numbered in the margin. */
  function remarks(findings, heading) {
    var r = el("div", "remarks");
    r.appendChild(el("h4", null, heading || "Remarks"));
    var ol = el("ol");
    findings.forEach(function (f, i) {
      var li = el("li", f.level);
      li.appendChild(el("i", null, String(i + 1)));
      var body = el("div");
      body.appendChild(el("b", null, sentence(f.title)));
      if (f.detail) body.appendChild(el("span", null, f.detail));
      li.appendChild(body);
      ol.appendChild(li);
    });
    r.appendChild(ol);
    return r;
  }

  /** A price for reading. Pools quote anything from a few billionths to millions, so the number of
      places follows the size of the number rather than a fixed two. */
  function fmtPrice(x) {
    var n = Number(x);
    if (!isFinite(n) || n <= 0) return null;
    if (n >= 1e12) return n.toExponential(3);
    if (n >= 1000) return fmt(n);
    if (n >= 1) return n.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
    if (n >= 1e-6) return n.toPrecision(4);
    return n.toExponential(3);
  }

  /** How far the price of token0 must move, in percent, to go from one tick to another. */
  function moveTo(fromTick, toTick) { return (Math.pow(1.0001, toTick - fromTick) - 1) * 100; }

  /** A price move for reading. Past a tenfold rise a percentage stops meaning anything and the
      move is a multiple; a fall can never pass a hundred percent, only approach it. */
  function pctText(x) {
    if (x >= 900) return "×" + fmtPrice(1 + x / 100);
    var a = Math.abs(x);
    var s = a < 1 ? a.toFixed(2) : a < 100 ? a.toFixed(1) : String(Math.round(a));
    if (x < 0 && a > 99.99) s = "99.99";
    return (x < 0 ? "−" : "+") + s + " %";
  }

  /** A range so wide it covers every price anybody will see. Said in words: its bounds printed as
      prices are numbers with fifty digits. */
  function everyPrice(tl, tu) { return tu - tl >= 400000; }

  /** "Earns between 2,675.81 and 2,785.01 USDG per ETH." */
  function rangeSentence(pos, s0, s1) {
    if (pos.tickLower == null) return null;
    if (everyPrice(pos.tickLower, pos.tickUpper)) {
      return "Earns at almost any price: ticks " + pos.tickLower + " to " + pos.tickUpper + ".";
    }
    if (pos.priceLower == null || pos.priceUpper == null) return null;
    return "Earns between " + fmtPrice(pos.priceLower) + " and " + fmtPrice(pos.priceUpper) + " " + s1 + " per " + s0 + ".";
  }

  /** The range drawn on the price line: the parcel between its two posts, the price as a pin, and
      the distance to each post. Everything is a percentage of the width, so it is the same drawing
      on a phone. The window is the range with a third of its width either side, widened to take
      the price in when the price has left it. */
  function survey(o) {
    var tl = o.tl, tu = o.tu, tick = o.tick;
    var width = Math.max(1, tu - tl), lo = tl - width * 0.35, hi = tu + width * 0.35;
    if (tick < lo) lo = tick - width * 0.12;
    if (tick > hi) hi = tick + width * 0.12;
    var x = function (t) { return Math.max(0, Math.min(100, (t - lo) / (hi - lo) * 100)); };
    var inside = tick >= tl && tick < tu;
    var priced = o.lower != null && o.upper != null && o.now != null;
    var bounded = priced && !everyPrice(tl, tu);
    var lowerT = bounded ? fmtPrice(o.lower) : "tick " + tl;
    var upperT = bounded ? fmtPrice(o.upper) : "tick " + tu;
    var nowT = priced ? o.base + " " + fmtPrice(o.now) : "tick " + tick;

    var s = el("div", "survey" + (inside ? "" : " out"));
    s.setAttribute("role", "img");
    s.setAttribute("aria-label", "Range " + lowerT + " to " + upperT + (priced ? " " + o.quote + " per " + o.base : "") +
      ". Price " + nowT + ", " + (inside ? "inside the range." : "outside it."));
    s.appendChild(el("span", "cap", priced ? "Price of " + o.base + ", in " + o.quote : "Range, in ticks"));
    s.appendChild(el("div", "ruler"));

    var parcel = el("div", "parcel");
    parcel.style.left = x(tl) + "%";
    parcel.style.width = (x(tu) - x(tl)) + "%";
    s.appendChild(parcel);
    [tl, tu].forEach(function (t) {
      var p = el("div", "post");
      p.style.left = x(t) + "%";
      s.appendChild(p);
    });

    var at = el("div", "at" + (x(tick) > 62 ? " flip" : ""));
    at.style.left = x(tick) + "%";
    at.appendChild(el("span", null, nowT));
    s.appendChild(at);

    function label(pos, text) {
      var l = el("span", "lab" + (pos < 8 ? " l" : pos > 92 ? " r" : ""), text);
      l.style.left = pos + "%";
      s.appendChild(l);
    }
    // Two labels need room; a range squeezed small by a price far away gets one.
    if (x(tu) - x(tl) >= 24) {
      label(x(tl), lowerT);
      label(x(tu), upperT);
    } else {
      label((x(tl) + x(tu)) / 2, lowerT + " – " + upperT);
    }

    // The words after the figure go first when the margin is narrow; the figure stays.
    function dim(a, b, text, warn, more) {
      var d = el("div", "dim" + (warn ? " warn" : ""));
      d.style.left = a + "%";
      d.style.width = Math.max(0, b - a) + "%";
      var t = el("span", null, text);
      if (more) t.appendChild(el("i", "more", more));
      d.appendChild(t);
      s.appendChild(d);
    }
    if (inside) {
      var down = moveTo(tick, tl), up = moveTo(tick, tu);
      var nearUp = Math.abs(up) <= Math.abs(down);
      dim(x(tl), x(tick), pctText(down), !nearUp);
      dim(x(tick), x(tu), pctText(up), nearUp, nearUp ? " to the edge" : null);
    } else if (tick < tl) {
      dim(x(tick), x(tl), pctText(moveTo(tick, tl)), true, " to come back");
    } else {
      dim(x(tu), x(tick), pctText(moveTo(tick, tu)), true, " to come back");
    }
    return s;
  }

  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  /** "29 Sep, 18:40 UTC". In UTC because that is the only clock the vault and every reader share. */
  function dateOf(unixSeconds) {
    var d = new Date(Number(unixSeconds) * 1000);
    var pad = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getUTCDate() + " " + MONTHS[d.getUTCMonth()] + ", " + pad(d.getUTCHours()) + ":" +
      pad(d.getUTCMinutes()) + " UTC";
  }

  /** A funded lease to scale: the term, then the grace window, what has already passed filled in,
      and a pin for now, read against the chain's clock. */
  function termLine(d) {
    var start = Number(d.fundedAt), end = start + Number(d.term), close = end + Number(d.grace);
    var nowAt = Math.max(0, Math.min(100, (chainNow - start) / (close - start) * 100));
    var wrap = el("div");
    var line = el("div", "term-line");
    line.setAttribute("role", "img");
    line.setAttribute("aria-label", "Lease from " + dateOf(start) + " to " + dateOf(end) +
      ", then a buy-back window until " + dateOf(close) + ".");
    var lease = el("div", "seg lease");
    lease.style.flexGrow = String(Number(d.term));
    lease.style.setProperty("--days", String(Math.max(1, Math.min(30, Math.round(Number(d.term) / 86400)))));
    var grace = el("div", "seg grace");
    grace.style.flexGrow = String(Number(d.grace));
    var done = el("div", "done");
    done.style.width = nowAt + "%";
    var pin = el("div", "now" + (nowAt < 4 ? " l" : nowAt > 96 ? " r" : ""));
    pin.style.left = nowAt + "%";
    pin.appendChild(el("span", null, "now"));
    [lease, grace, done, pin].forEach(function (n) { line.appendChild(n); });
    wrap.appendChild(line);

    var legend = el("div", "legend");
    [["Signed", start, false], ["Lease ends", end, true], ["Buy-back window closes", close, true]].forEach(function (x) {
      var item = el("div");
      item.appendChild(el("b", null, x[0]));
      item.appendChild(el("span", null, dateOf(x[1])));
      if (x[2]) item.appendChild(el("em", null, when(x[1])));
      legend.appendChild(item);
    });
    wrap.appendChild(legend);
    return wrap;
  }

  /** The deal in one sentence, its figures written into blanks. Parts are text, nodes, or
      { f: "text", hl: true } for a blank; hl marks the one figure the reader came for. */
  function contract(parts) {
    var p = el("p", "contract");
    parts.forEach(function (x) {
      if (typeof x === "string") p.appendChild(document.createTextNode(x));
      else if (x.nodeType) p.appendChild(x);
      else p.appendChild(el("span", "f" + (x.hl ? " hl" : ""), x.f));
    });
    return p;
  }

  /** An address inside a sentence. */
  function who(a) {
    var s = el("span", "who");
    s.appendChild(addr(a));
    return s;
  }

  /** What the vault will never do, pressed into every lease it holds. Each seal carries its own
      ring for the text to run along, because an id is only good once in a page. */
  var seals = 0;
  function seal() {
    var id = "seal-ring-" + (++seals);
    var s = svgEl("svg", { "class": "seal", viewBox: "0 0 150 150", "aria-hidden": "true" });
    var defs = svgEl("defs");
    defs.appendChild(svgEl("path", { id: id, d: "M75 75m-57 0a57 57 0 1 1 114 0a57 57 0 1 1-114 0" }));
    s.appendChild(defs);
    s.appendChild(svgEl("circle", { cx: "75", cy: "75", r: "71", "stroke-width": "1.5" }));
    s.appendChild(svgEl("circle", { cx: "75", cy: "75", r: "44", "stroke-width": "1" }));
    var text = svgEl("text");
    var path = svgEl("textPath", { href: "#" + id });
    path.textContent = "NO ORACLE · NO OWNER · NO FEE · NO DEBT ·";
    text.appendChild(path);
    s.appendChild(text);
    var g = svgEl("g", { transform: "translate(51 51) scale(.094)" });
    g.appendChild(svgEl("path", { "class": "curve", d: "M147 338C201.5 338 190.6 196 256 196S310.5 338 365 338",
                                  fill: "none", "stroke-width": "46", "stroke-linecap": "round" }));
    g.appendChild(svgEl("rect", { "class": "post", x: "70", y: "112", width: "44", height: "288", rx: "22" }));
    g.appendChild(svgEl("rect", { "class": "post", x: "398", y: "112", width: "44", height: "288", rx: "22" }));
    s.appendChild(g);
    return s;
  }

  /** The two signature lines of a deal, and the seal beside them. */
  function parties(d, me) {
    var p = el("div", "parties");
    function line(label, a, open) {
      var box = el("div", "party");
      box.appendChild(el("p", "k", label));
      var v = el("p", "v");
      if (open) v.textContent = open;
      else {
        v.appendChild(addr(a));
        if (same(a, me)) v.appendChild(el("em", null, "you"));
      }
      box.appendChild(v);
      p.appendChild(box);
    }
    line("Lessee", d.seller);
    var funded = d.financier && !/^0x0{40}$/i.test(d.financier);
    line("Financier", d.financier, funded ? null : "open to anyone");
    p.appendChild(seal());
    return p;
  }

  /** The pool's swap fee, or the fact that its hook sets one. */
  function feeLabel(pips, dynamic) {
    if (dynamic) return "Dynamic fee";
    var n = Number(pips);
    return isFinite(n) ? (n / 10000).toFixed(n % 100 ? 3 : 2).replace(/0+$/, "").replace(/\.$/, "") + " % fee" : null;
  }

  /** The token a pool is quoted in, read from the token itself. A symbol is whatever the token's
      author chose, so it is length-limited and printed as text, never markup. */
  var symbols = {};
  function bytesToText(h) { return decodeURIComponent(h.replace(/../g, function (b) { return "%" + b; })); }
  function symbolOf(address) {
    var a = String(address).toLowerCase();
    if (/^0x0{40}$/.test(a)) return Promise.resolve("ETH");
    if (!symbols[a]) {
      symbols[a] = call(address, window.TENURE_ABI.token["symbol()"]).then(function (data) {
        var hex = String(data || "").replace(/^0x/, "");
        var text = hex.length === 64
          ? bytesToText(hex).replace(/\u0000+$/, "")
          : bytesToText(hex.slice(128, 128 + parseInt(hex.slice(64, 128), 16) * 2));
        text = text.replace(/[\u0000-\u001f]/g, "").trim();
        return text ? text.slice(0, 12) : short(address);
      }).catch(function () { return short(address); });
    }
    return symbols[a];
  }

  /** Rent as a share of the price, over the term and scaled to a year. What a financier compares
      one listing with another on. Integer arithmetic until the very last step. */
  function rentOnPrice(d) {
    if (!d.price || d.price === 0n || !d.term) return null;
    var period = Number(d.rent * 1000000n / d.price) / 10000;
    return { period: period, yearly: period * 31536000 / Number(d.term) };
  }

  /** "1 deal has" / "4 deals have". A page that says "1 deals" was written by nobody. */
  function count(n, noun) {
    return n + " " + noun + (n === 1 ? " has" : "s have");
  }

  function same(a, b) { return !!a && !!b && a.toLowerCase() === b.toLowerCase(); }

  function usdg(units, places) { return Eth.fromUnits(units, DEC, places === undefined ? 2 : places); }

  /** The settlement token's ticker on the active chain. It is USDG on mainnet and a worthless
      stand-in on a test network, and a page that calls both USDG invites somebody to confuse
      them. */
  function tok() { return CFG.usdgSymbol; }

  function money2(units) { return usdg(units) + " " + tok(); }

  function duration(seconds) {
    var s = Math.abs(Math.round(Number(seconds)));
    if (s >= 86400) return Math.round(s / 86400) + (Math.round(s / 86400) === 1 ? " day" : " days");
    if (s >= 3600) return Math.round(s / 3600) + " h";
    if (s >= 60) return Math.round(s / 60) + " min";
    return s + " s";
  }

  /* Every deadline in the vault is compared against block.timestamp, so this page reads that
     clock rather than the one in the corner of the screen. A machine whose clock is a day out
     would otherwise be told a grace window is open that the chain considers closed. */
  var chainNow = Math.floor(Date.now() / 1000);

  async function readChainClock() {
    try {
      var block = await Eth.rpc(CFG.chain.rpc, "eth_getBlockByNumber", ["latest", false]);
      if (block && block.timestamp) chainNow = Number(BigInt(block.timestamp));
    } catch (e) { /* keep the last reading; a missed block is not worth an error on screen */ }
    return chainNow;
  }

  /** "in 6 days" / "5 h ago", against the chain's clock. */
  function when(unixSeconds) {
    var delta = Number(unixSeconds) - chainNow;
    return delta >= 0 ? "in " + duration(delta) : duration(delta) + " ago";
  }

  function row(parent, k, v, accent) {
    var r = el("div", "row");
    r.appendChild(el("span", "k", k));
    r.appendChild(el("span", "v" + (accent ? " am" : ""), v));
    parent.appendChild(r);
    return r;
  }

  /** A headline figure on a ledger line: label, number, unit beside it, a line of context under. */
  function tile(parent, k, v, unit, sub, accent) {
    var t = el("div", "tile" + (accent ? " am" : ""));
    t.appendChild(el("p", "k", k));
    var val = el("p", "v");
    val.appendChild(el("span", "n", v));
    if (unit && v !== "—") val.appendChild(el("small", null, unit));
    t.appendChild(val);
    if (sub) t.appendChild(el("p", "u", sub));
    parent.appendChild(t);
  }

  /** A figure fit to print, or null. Beyond about a quadrillion USDG nothing is a quantity of
      money any more, it is an overflowed counter, and toFixed answers those in scientific
      notation, which reads like a bug in this page rather than a broken counter in the pool. */
  function money(x, places) {
    var n = Number(x);
    if (!isFinite(n) || Math.abs(n) >= 1e15) return null;
    return n.toFixed(places === undefined ? 2 : places);
  }

  /** A figure for reading, with thousands separated. money() stays plain because it fills
      inputs, and an input holding "65,126.02" does not parse. */
  function fmt(x) {
    var m = money(x);
    if (m === null) return null;
    var parts = m.split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return parts.join(".");
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

  /** One place where every write happens, so every write reports the same way. `after` is handed
      the receipt, for the one write whose result is only in its logs. */
  async function act(button, label, to, data, after) {
    if (busy) return;
    busy = true;
    var original = button.textContent;
    button.disabled = true;
    button.textContent = label;
    quiet();
    try {
      var hash = await Wallet.send(to, data);
      button.textContent = (label.match(/^Step \d of \d · /) || [""])[0] + "waiting for the block…";
      var receipt = await Wallet.wait(hash);
      say(sentence(label.replace(/^Step \d of \d · /, "").replace(/…$/, "") + " done"), "ok", txLink(hash));
      if (after) await after(receipt);
    } catch (err) {
      var text = Eth.explain(err);
      if (text) say(text, "err");
    } finally {
      busy = false;
      button.disabled = false;
      button.textContent = original;
    }
  }

  /** Asks the test position faucet for a position, then hands its id to `then`. The id is read
      from the faucet's own event in the receipt rather than guessed from the PositionManager's
      counter, which anybody else's mint in the same block would move. */
  function testPositionButton(label, then) {
    var b = el("button", "ghost", label || "Get a test position");
    b.type = "button";
    b.title = "A live Uniswap v4 position in a pool of two test tokens, sent to your wallet. Worth nothing.";
    b.addEventListener("click", async function () {
      if (!Wallet.state.account) {
        try { await Wallet.connect(); } catch (err) { return say(Eth.explain(err) || "", "err"); }
      }
      await act(b, "opening a position…", CFG.faucet, window.TENURE_ABI.faucet["give()"], function (receipt) {
        var log = (receipt.logs || []).filter(function (l) {
          return same(l.address, CFG.faucet) && l.topics && l.topics[0] === window.TENURE_ABI.faucet.Given;
        })[0];
        if (!log) return;
        var id = BigInt(log.topics[2]).toString();
        say("Position " + id + " is yours. It is in range and ready to offer.", "ok");
        if (then) return then(id);
      });
    });
    return b;
  }

  /** Approvals are for the exact amount needed. An unlimited approval is convenient once and then
      permanent, and this vault is not special enough to deserve one. */
  async function ensureUsdgAllowance(button, amount) {
    var have = await usdgAllowance(Wallet.state.account);
    if (have >= amount) return "ready";
    var data = tokenData("approve(address,uint256)", ["address", "uint256"], [CFG.vault, amount]);
    var done = false;
    await act(button, "Step 1 of 2 · approving " + money2(amount) + "…", CFG.usdg, data, function () { done = true; });
    return done ? "approved" : false;
  }

  // ------------------------------------------------------------------ view: value

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

    // No valuation service on this chain: confirm the position exists and who holds it, then let
    // the seller write their own terms. The vault checks the rest.
    if (!CFG.api) {
      try {
        var owner = await positionOwner(id);
        renderUnpriced(id, owner);
      } catch (err) {
        say("No position with that id on this chain.", "err");
      } finally {
        btn.disabled = false;
        btn.textContent = "Check it";
      }
      return;
    }

    try {
      var res = await fetch(CFG.api + "/v1/position/" + id + "/quote");
      var data = await res.json();
      if (res.status === 404) return say("No position with that id on this chain.", "err");
      if (res.status === 402) {
        return say("The API is asking to be paid for this request. The public deployment runs " +
                   "free, so this is a different instance.", "err");
      }
      if (!res.ok) return say(data.message || data.error || "The chain could not be read right now.", "err");
      renderQuote(data);
      // Only the id changes. Rebuilding the query from scratch dropped the chain, so a shared or
      // reloaded valuation came back on the default chain.
      params.set("id", id);
      history.replaceState(null, "", "?" + params.toString() + (location.hash || ""));
    } catch (err) {
      say("Could not reach the valuation API: " + (err && err.message ? err.message : err), "err");
    } finally {
      btn.disabled = false;
      btn.textContent = CFG.api ? "Value it" : "Check it";
      withIcon(btn, "arrow", true);
    }
  }

  /** What can be shown about a position without a service to price it. */
  function renderUnpriced(tokenId, owner) {
    var out = $("result");
    out.textContent = "";

    var sh = sheet([ref("Position No.", tokenId), CFG.chain.name], "Not priced here");
    titleBlock(sh.body, "Position " + tokenId, "Held by " + short(owner) + ".");
    var rows = el("div", "rows");
    rowNode(rows, "Held by", addr(owner));
    if (CFG.usdg) {
      var token = el("span");
      token.appendChild(document.createTextNode(tok() + " · "));
      token.appendChild(addr(CFG.usdg));
      rowNode(rows, "Settlement token", token);
    } else {
      row(rows, "Settlement token", "none configured");
    }
    sh.body.appendChild(rows);
    var n = el("p", "note", "There is no valuation service on " + CFG.chain.name + ": it " +
      "prices positions in USDG by reading USDG pools, and this chain has none. What it holds and " +
      "what it earns are still on the chain; the terms below are yours to write, and the vault " +
      "refuses a listing it cannot settle.");
    n.style.marginTop = "18px";
    sh.body.appendChild(n);
    out.appendChild(sh.node);

    out.appendChild(listingPanel({ tokenId: tokenId, quote: null }));
  }

  function renderQuote(d) {
    var out = $("result");
    out.textContent = "";

    var pool = d.pool || {}, pos = d.position || {}, value = d.valueUSDG, price = d.price || {};
    var rate = d.feeRate || {}, quote = d.quote || {};
    var s0 = (pool.token0 && pool.token0.symbol) || "token0", s1 = (pool.token1 && pool.token1.symbol) || "token1";
    var readable = rate.available && rate.plausible !== false && money(rate.feesPerDayUSDG) !== null;
    var hooked = pool.hooks && !/^0x0{40}$/i.test(pool.hooks);

    // ---- the position
    var sh = sheet([ref("Position No.", d.tokenId), s0 + " · " + s1,
                    feeLabel(pool.keyFeePips, pool.keyFeePips === 8388608)],
                   hooked ? "Hook attached" : "No hook");
    // An emptied position is still "in range": its interval contains the price, it just holds
    // nothing. A green stamp on that says the opposite of what matters.
    var empty = pos.liquidity === "0";
    var stamps = [empty ? ["flat", "Empty"] : pos.inRange ? ["", "In range"] : ["bad", "Out of range"]];
    if (pos.hasSubscriber) stamps.push(["bad", "Subscriber"]);
    var between = rangeSentence(pos, s0, s1);
    if (between && price.token0InToken1 != null) between += " The price is " + fmtPrice(price.token0InToken1) + ".";
    titleBlock(sh.body, pairHeading(s0, s1), between, stamps);

    // The three figures somebody opened this screen for, before the detail they can check after.
    if (value) {
      var head = el("div", "tiles");
      tile(head, "Market value", fmt(value.total) || "—", tok(), "held and fees, at the pool's price", true);
      tile(head, "Fees per day", readable ? fmt(rate.feesPerDayUSDG) : "—", tok(),
           readable ? "measured, not modelled" : "not readable");
      tile(head, "Fee rate", readable && money(rate.feeAprPercent) !== null ? fmt(rate.feeAprPercent) + " %" : "—", null,
           "a year, from the last " + duration(rate.windowSeconds || 86400));
      sh.body.appendChild(head);
    }

    if (!empty && pos.tickLower != null && price.tick != null) {
      sh.body.appendChild(survey({ tl: pos.tickLower, tu: pos.tickUpper, tick: price.tick, lower: pos.priceLower,
                                   upper: pos.priceUpper, now: price.token0InToken1, base: s0, quote: s1 }));
    }

    var rows = el("div", "rows");
    var owner = rowNode(rows, "Owner", addr(pos.owner || d.owner || "—"));
    // Asked of the chain this page is configured for. The API answers about the chain it is
    // configured for, and the listing button acts on this one, so this is the row that has to be
    // right. They agree in production and they do not agree against a fork.
    positionOwner(d.tokenId).then(function (a) {
      var v = owner.querySelector(".v");
      v.textContent = "";
      v.appendChild(addr(a));
    }, function () { /* a node that will not answer leaves the API's reading in place */ });
    if (d.principal) row(rows, "Holds", fmtAmount(d.principal.amount0) + " " + s0 + " + " + fmtAmount(d.principal.amount1) + " " + s1);
    if (value) {
      row(rows, "Held, in " + tok(), (fmt(value.principal) || "—") + " " + tok());
      row(rows, "Uncollected fees", (fmt(value.fees) || "—") + " " + tok());
    } else if (d.valueNote) {
      row(rows, "Value", d.valueNote);
    }
    if (readable) {
      row(rows, "Fees per day", fmt(rate.feesPerDayUSDG) + " " + tok(), true);
      row(rows, "Measured over", duration(rate.windowSeconds) + " of chain history");
      row(rows, "Source", rate.source + (rate.lowConfidence ? " · low confidence" : ""));
    } else if (rate.available) {
      row(rows, "Fees per day", "not readable");
    }
    row(rows, "Ticks", pos.tickLower + " → " + pos.tickUpper);
    row(rows, "Liquidity", pos.liquidity);
    sh.body.appendChild(rows);

    if (rate.available && !readable) {
      // The counter this is read from is a wrapping accumulator, and a pool that has gone round
      // reports a rate no arithmetic can rescue. Printing it anyway would be the page inventing a
      // number; the honest line is the absence of one.
      var w = el("p", "note warn", "This pool's fee counter has wrapped around, so nothing can be " +
        "read from it about what the range earns. No terms are proposed from a number like that.");
      w.style.marginTop = "18px";
      sh.body.appendChild(w);
    } else if (!rate.available) {
      var r = el("p", "note", sentence(rate.reason || "No fee rate could be measured"));
      r.style.marginTop = "18px";
      sh.body.appendChild(r);
    }
    out.appendChild(sh.node);

    // ---- the terms, as the sentence they would be signed as
    var t = sheet(["Indicative terms", quote.available ? quote.termDays + " days" : null],
                  quote.available ? "Before anything is signed" : "None proposed");
    if (quote.available) {
      titleBlock(t.body, el("h2", null, "Could raise " + fmt(quote.suggestedSalePriceUSDG) + " " + tok() + "."));
      t.body.appendChild(contract([
        "Sold for ", { f: fmt(quote.suggestedSalePriceUSDG) + " " + tok(), hl: true },
        " and leased straight back for ", { f: quote.termDays + " days" },
        " at ", { f: fmt(quote.suggestedRentUSDG) + " " + tok() },
        " of rent, keeping every fee it earns. Bought back for ", { f: fmt(quote.suggestedBuybackPriceUSDG) + " " + tok() },
        ", never more than it was sold for."
      ]));
      var figs = el("div", "figs");
      fig(figs, "Sale price", fmt(quote.suggestedSalePriceUSDG) || "—", tok(), true);
      fig(figs, "Buyback", fmt(quote.suggestedBuybackPriceUSDG) || "—", tok());
      fig(figs, "Rent, " + quote.termDays + " days", fmt(quote.suggestedRentUSDG) || "—", tok());
      fig(figs, "Fees expected", fmt(quote.expectedFeesOverTermUSDG) || "—", tok());
      t.body.appendChild(figs);
      var note = "The buyback equals the sale price. The contract refuses any listing where it is " +
        "higher, so the financier is paid for the use of the asset and never for the passage of time.";
      if (quote.feeRateLowConfidence) note += " The rent rests on a narrow window of history; price it accordingly.";
      var pn = el("p", "fine", note);
      t.body.appendChild(pn);
    } else {
      titleBlock(t.body, "No terms for this one.");
      var nr = el("p", "note", sentence(quote.reason || "No terms could be derived") +
        " Offering it anyway would produce a listing the vault rejects.");
      nr.style.marginTop = "12px";
      t.body.appendChild(nr);
    }
    out.appendChild(t.node);

    // ---- offering it
    out.appendChild(listingPanel(d));
  }

  /** The seller's side. Shown only when there is a vault to list into and the terms are derivable;
      filled in from the quote, and every field is theirs to overwrite. */
  function listingPanel(d) {
    var sh = sheet(["Offer it", ref("Position", d.tokenId)], HAS_VAULT ? "You sign this" : "No vault yet");
    var node = sh.node, p = sh.body;

    if (!HAS_VAULT) {
      titleBlock(p, "Not on " + CFG.chain.name + " yet.");
      var nv = el("p", "note", "Listing needs the vault, and none is deployed on " +
        CFG.chain.name + " yet. When one is, this is where the terms above become an offer " +
        "somebody can fund.");
      nv.style.marginTop = "12px";
      p.appendChild(nv);
      return node;
    }
    // A position already inside a deal is held by the vault itself, and listing it again can only
    // be refused. Say where it is instead of offering a form that cannot work.
    positionOwner(d.tokenId).then(async function (owner) {
      if (!same(owner, CFG.vault)) return;
      var deals = await allDeals();
      var mine = deals.filter(function (x) { return x.tokenId === BigInt(d.tokenId); }).pop();
      p.textContent = "";
      titleBlock(p, "Already in a deal.", null, [["wait", mine ? "Deal " + mine.id : "In the vault"]]);
      var held = el("p", "note", "The vault holds this position" +
        (mine ? ", under deal " + mine.id : "") + ", so it cannot be offered again until that deal ends.");
      held.style.marginTop = "12px";
      p.appendChild(held);
      var bar = el("div", "acts");
      bar.appendChild(goTo("See your deals", "you", "primary"));
      bar.appendChild(goTo("Browse the market", "market", "ghost"));
      p.appendChild(bar);
    }).catch(function () { /* the vault's dry-run still refuses it, by name */ });

    var quote = d.quote || {};
    // A chain with no valuation service still has a vault. There, the terms are the seller's to
    // write, and the vault is the thing that checks them: every listing is dry-run with eth_call
    // first, so a refusal arrives named before any gas is spent.
    var priced = quote.available === true;
    if (!priced && CFG.api) {
      titleBlock(p, "Nothing to offer.");
      var nt = el("p", "note", "No terms could be derived for this position, so there is " +
        "nothing to offer. The vault would refuse the listing.");
      nt.style.marginTop = "12px";
      p.appendChild(nt);
      return node;
    }
    titleBlock(p, "Write the terms.", priced
      ? "Filled in from the valuation above. Every figure is yours to change."
      : "There is no valuation here, so the figures are yours. The vault refuses anything it cannot settle.");

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

    field("price", "Sale price · " + tok(), priced ? money(quote.suggestedSalePriceUSDG) : "",
          "What the financier pays you now.");
    field("buyback", "Buyback · " + tok(), priced ? money(quote.suggestedBuybackPriceUSDG) : "",
          "Never above the sale price.");
    field("rent", "Rent for the term · " + tok(), priced ? money(quote.suggestedRentUSDG) : "",
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
    field("builderFee", "Builder fee · " + tok(), "0", "At most a hundredth of the sale price.");
    field("maxFrozenBps", "Frozen time credited · bps", "5000",
          "Ceiling on how much of the term can stop the rent. At most 5000.");
    field("freezeProbe", "Freeze probe", "0", "0 never asks the pair whether it is frozen, 1 calls paused().");
    form = keep;
    adv.appendChild(form2);
    p.appendChild(adv);

    var bar = el("div", "acts");
    var go = el("button", "primary", "List this position");
    bar.appendChild(go);
    var why = el("p", "note");
    bar.appendChild(why);
    p.appendChild(bar);

    /** The contract is the authority on every one of these bounds. Checking them here only means
        somebody learns they got it wrong before they pay for a block, not instead of. */
    /** Reads one amount field and complains about that field rather than about parsing. On a chain
        with no valuation service these start empty, so this is the ordinary path, not the edge. */
    function amount(key, label) {
      var raw = inputs[key].value.trim();
      if (!raw) throw new Error("Fill in the " + label.toLowerCase() + ".");
      try {
        return Eth.toUnits(raw, DEC);
      } catch (err) {
        throw new Error("The " + label.toLowerCase() + " is not a number: " + raw);
      }
    }

    /** A duration typed in days or hours, returned in seconds. BigInt(NaN) throws a RangeError
        whose text is about JavaScript, so anything that is not a plain number is refused here. */
    function span(key, label, seconds) {
      var raw = inputs[key].value.trim();
      if (!/^\d+(\.\d+)?$/.test(raw)) {
        throw new Error("The " + label + " has to be a number" + (raw ? ", not " + raw : "") + ".");
      }
      return BigInt(Math.round(Number(raw) * seconds));
    }

    function whole(key, label) {
      var raw = inputs[key].value.trim();
      if (!/^\d+$/.test(raw)) {
        throw new Error("The " + label + " has to be a whole number" + (raw ? ", not " + raw : "") + ".");
      }
      return BigInt(raw);
    }

    function read() {
      var builder = inputs.builder.value.trim();
      if (!/^0x[0-9a-fA-F]{40}$/.test(builder)) {
        throw new Error("The builder is an address: forty hex characters after 0x, or the zero " +
                        "address for nobody.");
      }
      var t = {
        price: amount("price", "sale price"),
        rent: amount("rent", "rent"),
        buybackPrice: amount("buyback", "buyback"),
        term: span("termDays", "term", 86400),
        grace: span("graceHours", "grace window", 3600),
        listingDuration: span("listingDays", "offer duration", 86400),
        maxFrozenBps: whole("maxFrozenBps", "frozen-time ceiling"),
        freezeProbe: whole("freezeProbe", "freeze probe"),
        builder: builder,
        builderFee: amount("builderFee", "builder fee")
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
      else if (t.builderFee > 0n && /^0x0{40}$/i.test(t.builder)) bad = "A builder fee needs a builder to be paid to.";
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
      var twoSteps = !same(approved, CFG.vault);
      if (twoSteps) {
        var okd = false;
        var data = tokenData("approve(address,uint256)", ["address", "uint256"], [CFG.vault, d.tokenId]);
        await act(go, "Step 1 of 2 · approving the position…", CFG.posm, data, function () { okd = true; });
        if (!okd) return;
      }

      var fields = window.TENURE_ABI.struct.Terms.map(function (f) { return parsed.t[f[0]]; });
      var cd = Eth.calldata("list(uint256,(uint128,uint128,uint128,uint32,uint32,uint32,uint16,uint8,address,uint128))",
                            [d.tokenId, fields]);
      // act() re-enables its button when it finishes, which left a live "List" button under a
      // position that had already gone into the vault. The panel is replaced instead.
      var listedAs = null;
      await act(go, (twoSteps ? "Step 2 of 2 · " : "") + "listing…", CFG.vault, cd,
                async function () { listedAs = await vault("dealCount()"); });
      if (listedAs === null) return;
      p.textContent = "";
      titleBlock(p, "Offered.", null, [["wait", "Listed"]]);
      var offered = el("p", "note", "Listed as deal " + listedAs + ". It stays on the market until " +
        "somebody funds it or the offer expires, and you can cancel it until then.");
      offered.style.marginTop = "12px";
      p.appendChild(offered);
      var next = el("div", "acts");
      next.appendChild(goTo("See it on the market", "market", "primary"));
      p.appendChild(next);
    });

    why.textContent = "Listing hands the position to the vault. You keep collecting its fees for " +
      "the whole term, and you can buy it back at any time until the grace window closes.";
    return node;
  }

  // ------------------------------------------------------------------ view: market

  async function renderMarket() {
    var out = $("market");
    out.textContent = "";
    if (!HAS_VAULT) return out.appendChild(noVault());

    out.appendChild(loading("Reading the vault"));
    var deals;
    try {
      await readChainClock();
      deals = await allDeals();
    } catch (err) {
      out.textContent = "";
      return out.appendChild(el("p", "note", "The chain could not be read: " + (err.message || err)));
    }
    var open = deals.filter(function (d) {
      return Number(d.state) === 1 && Number(d.listingExpiry) > chainNow;
    });

    out.textContent = "";
    if (!open.length) {
      var p = emptyPanel("tag", deals.length
        ? "Nothing is on offer right now. " + count(deals.length, "deal") + " been listed here."
        : "Nothing has been listed on this vault yet.");
      p.appendChild(goTo("Offer a position", "value", "primary"));
      return out.appendChild(p);
    }
    open.forEach(function (d) { out.appendChild(dealCard(d, "market")); });
  }

  /** Why a payment cannot go ahead, and the way out when the money is only one step away: sitting
      in the vault, credited to this account, waiting to be withdrawn. */
  async function shortOf(what, need, have) {
    var text = what + " needs " + money2(need) + " and you hold " + money2(have) + ".";
    try {
      var owed = await vault("balances(address)", [Wallet.state.account]);
      if (have + owed >= need) text += " The vault holds " + money2(owed) + " for you: withdraw it on the You screen first.";
    } catch (e) { /* the reason above stands on its own */ }
    return text;
  }

  /** An empty screen with something to look at and somewhere to go. */
  function emptyPanel(icon, text) {
    var p = el("div", "empty");
    p.appendChild(withIcon(el("span", "badge"), icon));
    p.appendChild(el("p", null, text));
    return p;
  }

  function goTo(label, view, cls) {
    var b = el("button", (cls || "ghost") + " small", label);
    b.type = "button";
    b.addEventListener("click", function () { location.hash = "#" + view; });
    return b;
  }

  function noVault() {
    var p = emptyPanel("flask", "No vault is deployed on " + CFG.chain.name + " yet, so there is " +
      "nothing to read here. The valuation and the wallet view need no contract.");
    var bar = el("div", "bar");
    bar.appendChild(goTo("Value a position", "value", "primary"));
    bar.appendChild(goTo("See a wallet", "positions", "ghost"));
    p.appendChild(bar);
    return p;
  }

  // ------------------------------------------------------------------ view: you

  async function renderYou() {
    var out = $("you");
    out.textContent = "";
    if (!HAS_VAULT) return out.appendChild(noVault());

    var me = Wallet.state.account;
    if (!me) {
      var p = emptyPanel("wallet", "Connect a wallet to see the deals you are a party to.");
      var b = el("button", "primary small", "Connect wallet");
      b.addEventListener("click", doConnect);
      p.appendChild(b);
      return out.appendChild(p);
    }

    out.appendChild(loading("Reading the vault"));
    var deals, owed, held;
    try {
      await readChainClock();
      deals = await allDeals();
      owed = await vault("balances(address)", [me]);
      held = await usdgBalance(me);
    } catch (err) {
      out.textContent = "";
      return out.appendChild(el("p", "note", "The chain could not be read: " + (err.message || err)));
    }
    var mine = deals.filter(function (d) { return same(d.seller, me) || same(d.financier, me); });

    out.textContent = "";

    // What the vault is holding for this account, as a slip: one sentence, one button.
    var top = el("div", "held");
    var said = el("p");
    if (owed > 0n) {
      said.appendChild(document.createTextNode("The vault is holding "));
      said.appendChild(el("span", "f", money2(owed)));
      said.appendChild(document.createTextNode(" for you."));
    } else {
      said.textContent = "The vault is holding nothing for you right now.";
    }
    top.appendChild(said);
    if (owed > 0n) {
      var w = el("button", "primary", "Withdraw it");
      w.addEventListener("click", function () {
        act(w, "withdrawing…", CFG.vault, Eth.calldata("withdrawUSDG()", []), renderYou);
      });
      top.appendChild(w);
    }
    // A test network's settlement token is free to mint, and a deal cannot be tried without some.
    // Mainnet is excluded by id as well as by config: its token is money, and no button here
    // should ever look like it hands money out.
    if (CFG.testToken && CFG.chain.id !== 4663 && HAS_VAULT) {
      var amount = Eth.toUnits("10000", DEC);
      var mint = el("button", "ghost", "Get " + money2(amount));
      mint.title = tok() + " is a test token anyone can mint. It is worth nothing.";
      mint.addEventListener("click", function () {
        act(mint, "minting…", CFG.usdg, tokenData("mint(address,uint256)", ["address", "uint256"], [me, amount]),
            renderYou);
      });
      top.appendChild(mint);
    }
    if (HAS_FAUCET) {
      top.appendChild(testPositionButton(null, function (id) {
        location.hash = "#value";
        $("tokenId").value = id;
        return lookup();
      }));
    }
    top.appendChild(el("p", "fine", "In your wallet: " + money2(held) + "."));
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
      var p = el("div", "held");
      var said = el("p");
      said.appendChild(document.createTextNode("Position "));
      said.appendChild(el("span", "f", tokenId));
      said.appendChild(document.createTextNode(" is waiting for you in the vault."));
      p.appendChild(said);
      var b = el("button", "primary", "Withdraw the position");
      b.addEventListener("click", function () {
        act(b, "withdrawing…", CFG.vault, Eth.calldata("withdrawPosition(uint256)", [tokenId]), renderYou);
      });
      p.appendChild(b);
      p.appendChild(el("p", "fine", "Nothing expires; take it when you like."));
      out.appendChild(p);
    });

    if (!mine.length) {
      var none = emptyPanel("key", "You are not a party to any deal on this vault yet.");
      var bar = el("div", "bar");
      bar.appendChild(goTo("Browse the market", "market", "primary"));
      bar.appendChild(goTo("Offer a position", "value", "ghost"));
      none.appendChild(bar);
      out.appendChild(none);
      return;
    }
    mine.forEach(function (d) { out.appendChild(dealCard(d, "you")); });
  }

  // ------------------------------------------------------------------ a deal, and what you can do to it

  /** A deal as the lease it is: its references across the top, the contract in one sentence with
      the figures in its blanks, the term to scale while it runs, who signed it, and what the reader
      can do to it. Every figure is the vault's own; nothing here is estimated. */
  function dealCard(d, where) {
    var me = Wallet.state.account;
    var isSeller = same(d.seller, me);
    var isFinancier = same(d.financier, me);
    var now = chainNow;
    var st = Number(d.state);
    var days = duration(d.term);

    var pairRef = el("span", null, "…");
    Promise.all([symbolOf(d.currency0), symbolOf(d.currency1)]).then(function (s) {
      pairRef.textContent = s[0] + " · " + s[1];
    });
    var role = isSeller ? "You are the lessee" : isFinancier ? "You are the financier" : st === 1 ? "Open to fund" : null;
    var sh = sheet([ref("Deal No.", d.id), ref("Position", d.tokenId), pairRef], role);
    var card = sh.node, b = sh.body;

    function heading(main, faint) {
      var h = el("h2", null, main);
      if (faint) {
        h.appendChild(document.createTextNode(" "));
        h.appendChild(el("span", null, faint));
      }
      return h;
    }
    var heads = {
      1: heading("On offer,", "for " + days + "."),
      2: heading("Sold, leased back,", days + "."),
      3: heading("Bought back."),
      4: heading("Delivered", "to the financier."),
      5: heading("Withdrawn", "before anyone funded it.")
    };
    var look = st === 1 ? "wait" : st === 2 || st === 3 ? "" : "flat";
    titleBlock(b, heads[st] || heading("Deal " + d.id + "."), null,
               [[look, d.stateName.replace(/([a-z])([A-Z])/g, "$1 $2")]]);

    // The sentence names the reader as "you" wherever they are a party, and an address otherwise.
    function name(a, capital) { return same(a, me) ? (capital ? "You" : "you") : who(a); }
    var P = { f: money2(d.price) }, R = { f: money2(d.rent) }, B = { f: money2(d.buybackPrice) };
    var T = { f: days };
    var closes = Number(d.fundedAt) + Number(d.term) + Number(d.grace);
    var parts;
    if (st === 1 && isSeller) {
      P.hl = true;
      parts = ["You offer this position for ", P, " and would lease it back for ", T, " at ", R,
               " of rent, keeping every fee it earns, with the right to buy it back for ", B, " until ",
               { f: duration(d.grace) }, " after the lease ends. The offer closes ", { f: when(d.listingExpiry) }, "."];
    } else if (st === 1) {
      P.hl = true;
      parts = [who(d.seller), " offers this position for ", P, " and would lease it back for ", T, " at ", R,
               " of rent. Whoever funds it owns it outright, and is paid ", B, " if the lessee buys it back within ",
               { f: duration(d.grace) }, " of the lease ending. The offer closes ", { f: when(d.listingExpiry) }, "."];
    } else if (st === 2 && isFinancier) {
      R.hl = true;
      parts = ["You bought this position from ", who(d.seller), " for ", P, " and lease it to them for ", T,
               " at a rent of ", R, ". They may buy it back for ", B, " until ", { f: dateOf(closes) },
               "; after that it is yours to take."];
    } else if (st === 2) {
      B.hl = isSeller;
      parts = [name(d.seller, true), " sold this position to ", name(d.financier),
               " for ", P, isSeller ? " and lease it back for " : " and leases it back for ", T, " at a rent of ", R,
               ", keeping every fee it earns. ", isSeller ? "You may" : "The lessee may", " buy it back for ", B,
               " until ", { f: dateOf(closes) }, "."];
    } else if (st === 3) {
      parts = [name(d.seller, true), " sold this position to ", name(d.financier), " for ", P, ", leased it back for ", T,
               " at ", R, " of rent, and bought it back for ", B, "."];
    } else if (st === 4) {
      parts = ["The buy-back window closed without a buyback, so the position went to ", name(d.financier),
               ", who paid ", P, " for it and was owed ", R, " of rent."];
    } else {
      parts = [name(d.seller, true), " offered this position for ", P, " and withdrew the offer before anyone funded it."];
    }
    b.appendChild(contract(parts));

    if (st === 2) b.appendChild(termLine(d));

    var figs = el("div", "figs");
    fig(figs, "Sale price", usdg(d.price), tok());
    fig(figs, "Buyback", usdg(d.buybackPrice), tok(), st === 2 && isSeller);
    var r = rentOnPrice(d);
    fig(figs, "Rent on price", r ? r.period.toFixed(2) + " %" : "—", r ? "over " + days : null, false,
        r ? "about " + (r.yearly >= 100 ? Math.round(r.yearly) : r.yearly.toFixed(1)) + " % a year" : null);
    if (st === 1) fig(figs, "Offer closes", when(d.listingExpiry));
    else if (st === 2) fig(figs, "Rent credited", usdg(d.rentClaimed), "of " + money2(d.rent), isFinancier);
    else fig(figs, "Rent", usdg(d.rent), tok());
    b.appendChild(figs);

    if (st === 2 && (Number(d.pausedTotal) > 0 || Number(d.pausedSince) > 0)) {
      var rows = el("div", "rows");
      row(rows, "Frozen time recorded", duration(d.pausedTotal));
      b.appendChild(rows);
    }

    b.appendChild(parties(d, me));

    var acts = el("div", "acts");
    var any = false;

    function button(label, cls, fn) {
      var btn = el("button", (cls || "ghost") + " small", label);
      btn.addEventListener("click", function () { fn(btn); });
      acts.appendChild(btn);
      any = true;
      return btn;
    }

    // ---- listed
    if (st === 1) {
      if (!isSeller) {
        button("Fund it · " + money2(d.price), "primary", async function (btn) {
          if (!Wallet.state.account) {
            try { await Wallet.connect(); } catch (err) { return say(Eth.explain(err) || "", "err"); }
          }
          var have = await usdgBalance(Wallet.state.account);
          if (have < d.price) {
            return say(await shortOf("Funding this", d.price, have), "err");
          }
          var allowed = await ensureUsdgAllowance(btn, d.price);
          if (!allowed) return;
          await act(btn, (allowed === "approved" ? "Step 2 of 2 · " : "") + "funding…", CFG.vault,
                    Eth.calldata("fund(uint256)", [d.id]), refresh);
        });
      }
      if (isSeller) {
        button("Cancel the offer", "ghost", function (btn) {
          act(btn, "cancelling…", CFG.vault, Eth.calldata("cancel(uint256)", [d.id]), refresh);
        });
      }
    }

    // ---- active
    if (st === 2) {
      if (isSeller) {
        button("Buy it back · " + money2(d.buybackPrice), "primary", async function (btn) {
          var have = await usdgBalance(Wallet.state.account);
          if (have < d.buybackPrice) {
            return say(await shortOf("Buying it back", d.buybackPrice, have), "err");
          }
          var allowed = await ensureUsdgAllowance(btn, d.buybackPrice);
          if (!allowed) return;
          await act(btn, (allowed === "approved" ? "Step 2 of 2 · " : "") + "buying back…", CFG.vault,
                    Eth.calldata("buyBack(uint256)", [d.id]), refresh);
        });
        if (now <= Number(d.fundedAt) + Number(d.term)) {
          button("Collect the fees", "ghost", function (btn) {
            act(btn, "collecting…", CFG.vault, Eth.calldata("collectFees(uint256)", [d.id]), refresh);
          });
        }
      }
      if (isFinancier) {
        if (now >= closes) {
          button("Take delivery", "primary", function (btn) {
            act(btn, "releasing…", CFG.vault, Eth.calldata("release(uint256)", [d.id]), refresh);
          });
        }
        button("Claim the rent so far", "ghost", function (btn) {
          act(btn, "claiming…", CFG.vault, Eth.calldata("claimRent(uint256)", [d.id]), refresh);
        });
        // The financier owns the position outright, so they can sell that ownership on while the
        // lease runs. Nothing about the lease changes: same rent, same buyback, same dates, a
        // different counterparty. It is what makes a funded deal an asset rather than a lock-up,
        // and it is the reason the vault never needed a way to cancel one.
        button("Sell your side", "ghost", function () { openTransfer(b, d); });
      }
    }

    if (any) b.appendChild(acts);
    else if (where === "market" && st === 1 && isSeller) {
      var own = el("p", "fine", "This is your own listing, and the vault refuses to let you fund it.");
      b.appendChild(own);
    }
    return card;
  }

  /** The financier hands their side of a live deal to somebody else.

      The contract settles the rent accrued so far to the outgoing financier before changing the
      name, so nobody has to remember to claim first. It refuses the zero address, the vault
      itself and the lessee; the first two would strand the position and the third would put both
      sides of the deal in one pair of hands. */
  function openTransfer(card, d) {
    if (card.querySelector(".transfer")) return;

    var form = el("div", "transfer");
    var input = el("input");
    input.type = "text";
    input.placeholder = "Address of the new financier";
    input.spellcheck = false;
    input.autocomplete = "off";

    var go = el("button", "primary small", "Transfer");
    var cancel = el("button", "ghost small", "Cancel");
    var hint = el("span", "hint", "Rent accrued so far is settled to you first. The lease itself is " +
      "untouched: the lessee keeps the same rent, the same buyback price and the same dates.");

    form.appendChild(input);
    form.appendChild(go);
    form.appendChild(cancel);
    form.appendChild(hint);
    card.appendChild(form);
    input.focus();

    cancel.addEventListener("click", function () { card.removeChild(form); });

    function submit() {
      var to = input.value.trim();
      if (!/^0x[0-9a-fA-F]{40}$/.test(to)) {
        return say("That is not an address. It is forty hex characters after 0x.", "err");
      }
      act(go, "transferring…", CFG.vault,
          Eth.calldata("transferFinancierPosition(uint256,address)", [d.id, to]), refresh);
    }

    go.addEventListener("click", submit);
    input.addEventListener("keydown", function (e) { if (e.key === "Enter") submit(); });
  }


  // ------------------------------------------------------------------ positions

  /** A wallet's positions, from the valuation service. It reads the chain's transfer history to
      find them, so the first answer for a wallet takes a few seconds; the service keeps it warm. */
  var pfFilter = "all";

  function pfOwner() {
    var typed = $("pf-owner").value.trim();
    if (/^0x[0-9a-fA-F]{40}$/.test(typed)) return typed.toLowerCase();
    if (isLocal && /^0x[0-9a-fA-F]{40}$/.test(params.get("owner") || "")) return params.get("owner").toLowerCase();
    return Wallet.state.account ? Wallet.state.account.toLowerCase() : null;
  }

  /** An icon beside a label, from the sprite in the page. `after` puts it on the trailing side,
      which is where an icon that means "go" belongs. */
  function withIcon(node, icon, after) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "ico");
    var use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#i-" + icon);
    svg.appendChild(use);
    if (after) node.appendChild(svg);
    else node.insertBefore(svg, node.firstChild);
    return node;
  }

  /** One position in a wallet, as a sheet: its references, the range drawn on the price line,
      what it is worth and earns, and the remarks the chain supports about it. */
  function pfCard(p) {
    var worst = (p.findings || []).reduce(function (w, f) {
      var rank = { bad: 3, warn: 2, ok: 1, info: 0 };
      return rank[f.level] > rank[w] ? f.level : w;
    }, "info");
    var pool = p.pool || {}, pos = p.position || {}, price = p.price || {};
    var s0 = (pool.token0 && pool.token0.symbol) || "token0", s1 = (pool.token1 && pool.token1.symbol) || "token1";
    var hooked = pool.hooks && pool.hooks.address;
    var hookRef = el("span", null, hooked ? "Hook attached" : "No hook");
    if (hooked) hookRef.title = pool.hooks.permissions.join(", ") || "no permissions";
    var sh = sheet([ref("Position No.", p.tokenId), s0 + " · " + s1,
                    feeLabel(pool.feePips, pool.hooks && pool.hooks.dynamicFee)], hookRef);
    if (worst === "bad") sh.node.classList.add("bad");
    var b = sh.body;

    var liq = BigInt(pos.liquidity || "0");
    var stamp = liq === 0n ? ["flat", "Empty"] : pos.inRange ? ["", "In range"] : ["bad", "Out of range"];
    var between = liq === 0n ? "Holds nothing. Its fees, if any, are still waiting." : rangeSentence(pos, s0, s1);
    titleBlock(b, pairHeading(s0, s1), between, [stamp]);

    if (liq !== 0n && price.tick != null) {
      b.appendChild(survey({ tl: pos.tickLower, tu: pos.tickUpper, tick: price.tick, lower: pos.priceLower,
                             upper: pos.priceUpper, now: price.token0InToken1, base: s0, quote: s1 }));
    }

    var v = p.valueUSDG || {}, earn = p.earning || {};
    var figs = el("div", "figs");
    fig(figs, "Value", v.total != null ? fmt(v.total) : "—", "USDG");
    fig(figs, "Fees waiting", v.fees != null ? fmt(v.fees) : "—", "USDG");
    fig(figs, "Earned, last day", earn.feesPerDayUSDG != null ? fmt(earn.feesPerDayUSDG) : "—", "USDG");
    fig(figs, "Rate, last day", earn.feeAprPercent != null ? fmt(earn.feeAprPercent) + " %" : "—", "a year", true);
    b.appendChild(figs);

    if ((p.findings || []).length) b.appendChild(remarks(p.findings));

    var acts = el("div", "acts");
    function value() {
      location.hash = "#value";
      $("tokenId").value = String(p.tokenId);
      lookup();
    }
    var lease = p.lease || {};
    if (lease.available && HAS_VAULT) {
      var raise = el("button", "primary small", "Raise " + fmt(lease.suggestedSalePriceUSDG) + " " + tok() + " on it");
      raise.addEventListener("click", value);
      acts.appendChild(raise);
    }
    var val = withIcon(el("button", (lease.available && HAS_VAULT ? "ghost" : "primary") + " small", "Value it in full"), "search");
    val.addEventListener("click", value);
    acts.appendChild(val);
    if (CFG.chain.explorer) {
      var ex = el("a", "link", "On the explorer ↗");
      ex.href = CFG.chain.explorer.replace(/\/$/, "") + "/token/" + CFG.posm + "/instance/" + p.tokenId;
      ex.target = "_blank";
      ex.rel = "noopener";
      acts.appendChild(ex);
    }
    b.appendChild(acts);
    return sh.node;
  }

  async function renderPositions() {
    var out = $("positions");
    out.textContent = "";
    if (!CFG.api) {
      var na = el("div", "panel");
      na.appendChild(el("p", "note", "The wallet view is read by the valuation service, which runs on Robinhood Chain mainnet. "
        + "There are no USDG pools on " + CFG.chain.name + " to value positions against."));
      return out.appendChild(na);
    }
    var owner = pfOwner();
    if (!owner) {
      var p = emptyPanel("wallet", "Connect a wallet to see its positions, or paste any address above: this screen only reads.");
      var b = el("button", "primary small", "Connect wallet");
      b.addEventListener("click", doConnect);
      p.appendChild(b);
      return out.appendChild(p);
    }
    out.appendChild(loading("Finding the positions of " + short(owner)
      + ". The first look at a wallet reads its whole history and can take a few seconds", 4));
    out.appendChild(loading("Reading each position", 4));
    var body;
    try {
      var res = await fetch(CFG.api + "/v1/owner/" + owner + "/positions");
      if (res.status === 402) throw new Error("The valuation service asks for payment on this route right now.");
      if (!res.ok) throw new Error("The valuation service could not read the chain right now. Try again in a moment.");
      body = await res.json();
    } catch (e) {
      out.textContent = "";
      var er = el("div", "panel");
      er.appendChild(el("p", "note", e.message || "The valuation service did not answer."));
      return out.appendChild(er);
    }
    if (pfOwner() !== owner) return; // the wallet changed while this was in flight
    out.textContent = "";

    var s = body.summary;
    var tiles = el("div", "tiles four");
    tile(tiles, "Positions", String(s.positions), null,
         s.inRange + " in range" + (s.outOfRange ? ", " + s.outOfRange + " out" : "") + (s.empty ? ", " + s.empty + " empty" : ""));
    tile(tiles, "Value", fmt(s.valueUSDG), "USDG", "at each pool's own price", true);
    tile(tiles, "Fees waiting", fmt(s.uncollectedFeesUSDG), "USDG", "yours to collect");
    tile(tiles, "Earned, last day", s.feesPerDayUSDG != null ? fmt(s.feesPerDayUSDG) : "—", "USDG", "measured on the chain");
    out.appendChild(tiles);
    if (!s.complete || (body.truncated || []).length || (body.unreadable || []).length) {
      var notes = [];
      if (!s.complete) notes.push("This wallet has received more positions than can be listed at once; these are its most recent.");
      if ((body.truncated || []).length) notes.push(body.truncated.length + " more are held and not valued here.");
      if ((body.unreadable || []).length) notes.push(body.unreadable.length + " could not be read just now.");
      var nn = el("p", "note", notes.join(" "));
      nn.style.marginBottom = "24px";
      out.appendChild(nn);
    }
    if (!(body.positions || []).length) {
      return out.appendChild(emptyPanel("search",
        short(owner) + " holds no Uniswap v4 position on " + CFG.chain.name + "."));
    }

    var groups = {
      all: function () { return true; },
      attention: function (x) { return x.findings.some(function (f) { return f.level === "bad" || f.level === "warn"; }); },
      out: function (x) { return !x.position.inRange && x.position.liquidity !== "0"; },
      tenure: function (x) { return x.lease && x.lease.available; },
    };
    var labels = { all: "All", attention: "Needs a look", out: "Out of range", tenure: "Could raise cash" };
    var filters = el("div", "filters");
    var list = el("div");
    function paint() {
      list.textContent = "";
      body.positions.filter(groups[pfFilter]).forEach(function (x) { list.appendChild(pfCard(x)); });
      Array.prototype.forEach.call(filters.children, function (b) { b.setAttribute("aria-pressed", String(b.dataset.f === pfFilter)); });
    }
    Object.keys(groups).forEach(function (k) {
      var n = body.positions.filter(groups[k]).length;
      if (k !== "all" && !n) return;
      var b = el("button", null, labels[k]);
      b.type = "button";
      b.dataset.f = k;
      b.appendChild(el("b", null, String(n)));
      b.addEventListener("click", function () { pfFilter = k; paint(); });
      filters.appendChild(b);
    });
    if (!groups[pfFilter] || !body.positions.filter(groups[pfFilter]).length) pfFilter = "all";
    out.appendChild(filters);
    out.appendChild(list);
    paint();
    out.appendChild(el("p", "fine", body.disclaimer + " " + s.note));
  }

  // ------------------------------------------------------------------ testnet quests

  /** The seven things a tester can do to the vault, in the order a deal meets them. Each is read
      from an event the vault emits, so nothing here is self-reported and anyone can recount it. */
  var QUESTS = [
    ["listed", "Offer a position", "List a position on the vault, on terms you write."],
    ["funded", "Fund an offer", "Buy somebody's position and lease it straight back to them."],
    ["collected", "Collect the fees", "As the lessee, take the fees your leased position earned."],
    ["claimed", "Claim the rent", "As the financier, take the rent accrued so far."],
    ["boughtBack", "Buy it back", "Pay the buyback price and take your position home."],
    ["soldSide", "Sell your side", "Hand your side of a live lease to another address."],
    ["delivered", "Take delivery", "Let a buy-back window close, and take the position you own."]
  ];

  function hex(n) { return "0x" + n.toString(16); }

  /** Every quest event the vault has emitted, oldest first. Read in windows the public node
      accepts, from the block the vault was deployed in. */
  async function vaultEvents() {
    var ev = window.TENURE_ABI.ev;
    var names = ["Listed", "Funded", "FeesCollected", "RentClaimed", "BoughtBack", "FinancierTransferred", "Released"];
    var latest = Number(BigInt(await Eth.rpc(CFG.chain.rpc, "eth_blockNumber", [])));
    var start = CFG.fromBlock || 0, step = 500000, out = [];
    for (var from = start; from <= latest; from += step) {
      var logs = await Eth.rpc(CFG.chain.rpc, "eth_getLogs", [{
        address: CFG.vault, fromBlock: hex(from), toBlock: hex(Math.min(latest, from + step - 1)),
        topics: [names.map(function (n) { return ev[n]; })]
      }]);
      out = out.concat(logs || []);
    }
    out.sort(function (a, b) {
      return Number(BigInt(a.blockNumber) - BigInt(b.blockNumber)) || Number(BigInt(a.logIndex) - BigInt(b.logIndex));
    });
    return out;
  }

  /** address -> { quest: true }, from the events in order. A buyback is the lessee's and a
      delivery the financier's at that moment, so both sides of every deal are followed through
      funding and every hand-over. */
  function questProgress(logs) {
    var byTopic = {};
    Object.keys(window.TENURE_ABI.ev).forEach(function (n) { byTopic[window.TENURE_ABI.ev[n]] = n; });
    var done = {}, order = [], seller = {}, financier = {}, counts = { deals: 0, funded: 0 };
    function mark(a, q) {
      if (!a) return;
      a = a.toLowerCase();
      if (!done[a]) { done[a] = {}; order.push(a); }
      done[a][q] = true;
    }
    function topicAddr(l, i) { return "0x" + l.topics[i].slice(26); }
    logs.forEach(function (l) {
      var name = byTopic[l.topics[0]];
      var id = BigInt(l.topics[1]).toString();
      if (name === "Listed") { seller[id] = topicAddr(l, 2); counts.deals++; mark(seller[id], "listed"); }
      else if (name === "Funded") { financier[id] = topicAddr(l, 2); counts.funded++; mark(financier[id], "funded"); }
      else if (name === "FeesCollected") mark(topicAddr(l, 2), "collected");
      else if (name === "RentClaimed") mark(topicAddr(l, 2), "claimed");
      else if (name === "BoughtBack") mark(seller[id], "boughtBack");
      else if (name === "FinancierTransferred") { mark(topicAddr(l, 2), "soldSide"); financier[id] = topicAddr(l, 3); }
      else if (name === "Released") mark(financier[id], "delivered");
    });
    var rows = order.map(function (a, i) {
      var n = QUESTS.filter(function (q) { return done[a][q[0]]; }).length;
      return { address: a, done: done[a], n: n, both: !!(done[a].listed && done[a].funded), first: i };
    }).sort(function (x, y) { return y.n - x.n || x.first - y.first; });
    return { rows: rows, counts: counts };
  }

  async function renderQuests() {
    var out = $("quests");
    out.textContent = "";
    if (!TESTNET || !HAS_VAULT) {
      var off = emptyPanel("flask", "The quests run on Robinhood testnet, where the vault settles in a test token anyone can mint.");
      var bar = el("div", "bar");
      var go = el("button", "primary small", "Switch to the testnet");
      go.type = "button";
      go.addEventListener("click", function () { pinned = true; switchTo(46630); location.hash = "#quests"; });
      bar.appendChild(go);
      off.appendChild(bar);
      return out.appendChild(off);
    }
    out.appendChild(loading("Reading every deal the vault has seen", 4));
    var result;
    try {
      result = questProgress(await vaultEvents());
    } catch (err) {
      out.textContent = "";
      return out.appendChild(emptyPanel("no-oracle", "The testnet could not be read just now: " + (err.message || err)));
    }
    if (current() !== "quests") return;
    out.textContent = "";

    var rows = result.rows;
    var tiles = el("div", "tiles four");
    tile(tiles, "Testers", String(rows.length), null, "addresses with a quest done");
    tile(tiles, "Deals offered", String(result.counts.deals), null, "on this vault");
    tile(tiles, "Leases funded", String(result.counts.funded), null, "both sides signed");
    tile(tiles, "All seven", String(rows.filter(function (r) { return r.n === QUESTS.length; }).length), null,
         "founding testers", true);
    out.appendChild(tiles);

    // ---- the reader's own progress
    var me = Wallet.state.account && Wallet.state.account.toLowerCase();
    var mine = me && rows.filter(function (r) { return r.address === me; })[0];
    var sh = sheet([ref("Your quests", me ? short(me) : "no wallet"), CFG.chain.name],
                   mine ? mine.n + " of " + QUESTS.length : "0 of " + QUESTS.length);
    if (!me) {
      titleBlock(sh.body, "Connect to see your progress.", "Progress is read from the vault for the connected address. Nothing is stored anywhere else.");
      var c = el("div", "acts");
      var cb = el("button", "primary small", "Connect wallet");
      cb.addEventListener("click", doConnect);
      c.appendChild(cb);
      sh.body.appendChild(c);
    } else {
      var n = mine ? mine.n : 0;
      var stamps = n === QUESTS.length ? [["", "All seven"]] : mine && mine.both ? [["wait", "Both sides"]] : [];
      titleBlock(sh.body, n === QUESTS.length ? "Every one of them." : n + " of " + QUESTS.length + " done.",
                 n === QUESTS.length ? "You are on the list of founding testers." : "Each is checked on the chain the moment it happens.", stamps);
      sh.body.appendChild(remarks(QUESTS.map(function (q) {
        var did = mine && mine.done[q[0]];
        return { level: did ? "ok" : "info", title: q[1], detail: did ? "Done, and on the chain." : q[2] };
      }), "Quests"));
      var acts = el("div", "acts");
      if (HAS_FAUCET) {
        acts.appendChild(testPositionButton(null, function (id) {
          location.hash = "#value";
          $("tokenId").value = id;
          return lookup();
        }));
      }
      acts.appendChild(goTo("Fund an offer", "market", "ghost"));
      acts.appendChild(goTo("Your deals", "you", "ghost"));
      sh.body.appendChild(acts);
    }
    out.appendChild(sh.node);

    // ---- everyone
    var board = sheet(["The board", "read from the vault's events"], rows.length + (rows.length === 1 ? " tester" : " testers"));
    if (!rows.length) {
      titleBlock(board.body, "Nobody yet.", "The first address to offer a position on this vault goes at the top.");
    } else {
      var wrap = el("div", "board-wrap");
      var table = el("table", "board");
      var head = el("tr");
      head.appendChild(el("th", null, "Address"));
      QUESTS.forEach(function (q, i) {
        var th = el("th", "q", String(i + 1));
        th.title = q[1];
        head.appendChild(th);
      });
      head.appendChild(el("th", "n", "Done"));
      var thead = el("thead");
      thead.appendChild(head);
      table.appendChild(thead);
      var tbody = el("tbody");
      rows.slice(0, 200).forEach(function (r) {
        var tr = el("tr", r.address === me ? "me" : null);
        var td = el("td", "a");
        td.appendChild(addr(r.address));
        if (r.n === QUESTS.length) td.appendChild(el("span", "tag", "all seven"));
        else if (r.both) td.appendChild(el("span", "tag", "both sides"));
        tr.appendChild(td);
        QUESTS.forEach(function (q) {
          var cell = el("td", "q");
          var dot = el("i", r.done[q[0]] ? "on" : null);
          dot.title = q[1] + (r.done[q[0]] ? ": done" : ": not yet");
          cell.appendChild(dot);
          tr.appendChild(cell);
        });
        tr.appendChild(el("td", "n", r.n + " / " + QUESTS.length));
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      wrap.appendChild(table);
      board.body.appendChild(wrap);
      var legend = el("p", "fine", QUESTS.map(function (q, i) { return (i + 1) + ". " + q[1]; }).join("  ·  "));
      board.body.appendChild(legend);
    }
    out.appendChild(board.node);

    var fine = el("p", "fine");
    fine.appendChild(document.createTextNode("Counted from the vault's own events since block " + (CFG.fromBlock || 0) +
      ". What the quests count toward is set out in the "));
    var link = el("a", null, "docs");
    link.href = "https://docs-production-3405.up.railway.app/guide/testnet#quests";
    link.target = "_blank";
    link.rel = "noopener";
    fine.appendChild(link);
    fine.appendChild(document.createTextNode("."));
    out.appendChild(fine);
  }

  // ------------------------------------------------------------------ routing

  var VIEWS = ["value", "positions", "market", "you", "quests"];

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
    if (name === "positions") renderPositions();
    if (name === "quests") renderQuests();
  }

  function current() { return (location.hash || "#value").slice(1); }

  function refresh() {
    var v = current();
    if (v === "market") return renderMarket();
    if (v === "you") return renderYou();
    if (v === "positions") return renderPositions();
    if (v === "quests") return renderQuests();
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
    // A wallet sitting on a chain this page is configured for is not a mismatch, it is a choice.
    // Follow it rather than telling somebody their own network is wrong.
    if (s.account && s.chainId && s.chainId !== CFG.chain.id && window.TENURE.chains[String(s.chainId)]
        && !pinned) {
      return switchTo(s.chainId);
    }
    // The chain is already named by the selector and the account by the wallet button, so the
    // network indicator only appears when something needs doing, and it is the thing to click.
    connect.textContent = "";
    if (s.account) {
      // A mark derived from the address itself, so two accounts are never mistaken for each other.
      var dot = el("span", "dot");
      var hue = parseInt(s.account.slice(2, 8), 16) % 360;
      dot.style.background = "conic-gradient(from 140deg, hsl(" + hue + " 70% 62%), hsl(" +
        ((hue + 80) % 360) + " 70% 58%), hsl(" + ((hue + 200) % 360) + " 70% 60%), hsl(" + hue + " 70% 62%))";
      connect.appendChild(dot);
      connect.appendChild(document.createTextNode(short(s.account)));
    } else {
      connect.textContent = "Connect wallet";
    }
    connect.title = s.account || "";
    var wrong = !!s.account && !!s.chainId && s.chainId !== CFG.chain.id;
    net.classList.toggle("hidden", !wrong);
    if (wrong) net.textContent = "Switch to " + CFG.chain.name;
  }

  function paintDevBanner() {
    $("dev").classList.remove("hidden");
    $("dev-vault").textContent = CFG.vault || "none";
    var sel = $("dev-account");
    Wallet.provider().accounts().forEach(function (a, i) {
      var o = el("option", null, (i === 0 ? "seller " : i === 1 ? "financier " : "account " + i + " ") + short(a));
      o.value = String(i);
      if (i === CFG.devAccount) o.selected = true;
      sel.appendChild(o);
    });
    sel.addEventListener("change", function () {
      Wallet.provider().use(Number(sel.value));
      refresh();
    });
  }

  /** Changing chain rebuilds the configuration and redraws; the url carries it so the page can
      be reloaded or shared on the chain it was read on. */
  function switchTo(id) {
    if (!useChain(id)) return;
    // The wallet layer holds its own copy of the configuration, so it has to be told too.
    Wallet.init(CFG);
    params.set("chain", String(id));
    history.replaceState(null, "", "?" + params.toString() + (location.hash || ""));
    paintChrome();
    $("result").textContent = "";
    show(current());
  }

  function paintChrome() {
    // The quests tab exists where there are quests to do. A link straight to #quests still
    // works anywhere, and there it offers the switch.
    $("tab-quests").classList.toggle("hidden", !(TESTNET && HAS_VAULT));
    var ids = configuredChains();
    var sel = $("chain");
    sel.classList.toggle("hidden", ids.length < 2);
    sel.textContent = "";
    ids.forEach(function (id) {
      var o = el("option", null, window.TENURE.chains[String(id)].name);
      o.value = String(id);
      if (id === CFG.chain.id) o.selected = true;
      sel.appendChild(o);
    });
    var foot = $("foot");
    foot.textContent = "";
    if (HAS_VAULT) {
      foot.appendChild(document.createTextNode("Vault "));
      var v = addr(CFG.vault);
      v.textContent = short(CFG.vault); // "Vault the vault" otherwise: here it is named already
      foot.appendChild(v);
      foot.appendChild(document.createTextNode(" on " + CFG.chain.name + ". "));
    } else {
      foot.textContent = "No contract is deployed on " + CFG.chain.name +
        " yet, so nothing here can be listed or funded. ";
    }
    paintValueScreen();
    paintWallet(Wallet.state);
  }

  $("chain").addEventListener("change", function () { pinned = true; switchTo(Number(this.value)); });
  $("connect").addEventListener("click", doConnect);
  $("net").addEventListener("click", function () {
    Wallet.switchChain().then(function () { quiet(); refresh(); }, function (err) {
      var text = Eth.explain(err);
      if (text) say(text, "err");
    });
  });
  $("lookup").addEventListener("click", lookup);
  $("tokenId").addEventListener("keydown", function (e) { if (e.key === "Enter") lookup(); });
  Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (t) {
    t.addEventListener("click", function () { location.hash = "#" + t.dataset.go; });
  });
  window.addEventListener("hashchange", function () { show(current()); });
  $("pf-go").addEventListener("click", renderPositions);
  $("pf-owner").addEventListener("keydown", function (e) { if (e.key === "Enter") renderPositions(); });
  // A wallet that connects, disconnects or changes account while this screen is open is a new question.
  var lastAccount = null;
  Wallet.on(function (s) {
    if ((s.account || null) === lastAccount) return;
    lastAccount = s.account || null;
    if (current() === "positions" && !$("pf-owner").value.trim()) renderPositions();
  });

  /** The opening screen is a valuation where there is a service to do it, and an offer where
      there is not. Saying which avoids a button called "Value it" that values nothing. */
  function paintValueScreen() {
    var section = document.querySelector('[data-view="value"]');
    var h1 = section.querySelector("h1");
    h1.textContent = CFG.api ? "What is it " : "What would you ";
    h1.appendChild(el("em", null, CFG.api ? "worth?" : "offer it for?"));
    section.querySelector(".eyebrow").textContent = CFG.api
      ? "No. 01 — Valuation, read from the chain" : "No. 01 — An offer, on " + CFG.chain.name;
    section.querySelector(".lede").textContent = CFG.api
      ? "Paste the id of a Uniswap v4 position and see what it holds, what its range has actually " +
        "earned, and the terms it could be offered on. Nothing is signed here."
      : "Paste the id of a Uniswap v4 position you hold on " + CFG.chain.name + " and write the " +
        "terms you would offer it on. There is no valuation service on this chain, so the figures " +
        "are yours; the vault refuses anything it cannot settle.";
    var lookupBtn = $("lookup");
    lookupBtn.textContent = CFG.api ? "Value it" : "Check it";
    withIcon(lookupBtn, "arrow", true);
    document.querySelector('[data-go="value"] span').textContent = CFG.api ? "Value" : "Offer";
    $("tokenId").placeholder = "Position id" + ((CFG.examples || [])[0] ? ", for example " + CFG.examples[0] : "");

    var tryIt = $("try");
    tryIt.textContent = "";
    // On a test network the useful first step is a position of your own: the examples belong to
    // somebody else, and only an owner can offer one.
    if (HAS_FAUCET) {
      tryIt.appendChild(el("span", null, "No position on " + CFG.chain.name + " yet?"));
      var get = testPositionButton(null, function (id) { $("tokenId").value = id; return lookup(); });
      get.classList.add("small");
      tryIt.appendChild(get);
    } else if ((CFG.examples || []).length) {
      tryIt.appendChild(el("span", null, "Try one:"));
      CFG.examples.forEach(function (id) {
        var chip = el("button", "chip", id);
        chip.type = "button";
        chip.addEventListener("click", function () { $("tokenId").value = id; lookup(); });
        tryIt.appendChild(chip);
      });
    }
  }

  Wallet.init(CFG);
  Wallet.on(paintWallet);
  paintChrome();
  show(current());

  // Then pick up an authorisation already given and draw the screen again, because the first
  // draw happened before the wallet had answered.
  Wallet.restore().then(function (account) {
    if (CFG.devWallet) paintDevBanner();
    if (account) refresh();
  }, function (err) {
    if (CFG.devWallet) say("The development chain did not answer: " + (err.message || err), "err");
  });

  // A position id in the address bar makes a valuation shareable.
  var fromUrl = params.get("id");
  if (fromUrl) {
    $("tokenId").value = fromUrl;
    lookup();
  }
})();
