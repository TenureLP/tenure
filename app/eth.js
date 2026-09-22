/* Everything the page needs to talk to a chain, written out rather than imported.

   The vault's whole surface is static ABI types: no arrays, no bytes, no strings, no nested
   structs. That is not a coincidence of this file, it is a property of the contract, and
   make-abi-js.py refuses to generate a table if it ever stops being true. So the coder below
   handles exactly the static case: a run of 32-byte words, one per value. Anything dynamic throws
   rather than silently producing calldata that means something else.

   Reads go over plain JSON-RPC, so the page works with no wallet at all. Writes go through the
   wallet, because that is the only place a key should be. */

window.Eth = (function () {
  "use strict";

  var ABI = window.TENURE_ABI;

  // ------------------------------------------------------------------ hex and words

  function strip(hex) {
    return String(hex || "").replace(/^0x/i, "");
  }

  function word(hex) {
    hex = strip(hex);
    if (hex.length > 64) throw new Error("value wider than a word");
    return "0".repeat(64 - hex.length) + hex;
  }

  /** Two's complement is not needed: no signed type appears anywhere in this contract's surface. */
  function encodeOne(type, value) {
    if (/^uint(\d+)?$/.test(type)) {
      var n = BigInt(value);
      if (n < 0n) throw new Error(type + " cannot be negative");
      return word(n.toString(16));
    }
    if (type === "address") {
      var a = strip(value);
      if (!/^[0-9a-f]{40}$/i.test(a)) throw new Error("not an address: " + value);
      // Lower case, as every other encoder writes it. Hex is case-insensitive to the EVM, but the
      // bytes a wallet shows and signs should have one form, not whatever case was pasted in.
      return word(a.toLowerCase());
    }
    if (type === "bytes32") {
      var b = strip(value);
      if (!/^[0-9a-f]{64}$/i.test(b)) throw new Error("not a bytes32: " + value);
      return b.toLowerCase();
    }
    if (type === "bool") return word(value ? "1" : "0");
    throw new Error("this coder only handles static types, not " + type);
  }

  function decodeOne(type, w) {
    if (/^uint(\d+)?$/.test(type)) return BigInt("0x" + w);
    if (type === "address") return "0x" + w.slice(24);
    if (type === "bytes32") return "0x" + w;
    if (type === "bool") return BigInt("0x" + w) !== 0n;
    throw new Error("this coder only handles static types, not " + type);
  }

  function words(data) {
    var hex = strip(data);
    var out = [];
    for (var i = 0; i + 64 <= hex.length; i += 64) out.push(hex.slice(i, i + 64));
    return out;
  }

  // ------------------------------------------------------------------ calldata

  function fn(sig) {
    var f = ABI.fn[sig];
    if (!f) throw new Error("no such function in the generated table: " + sig);
    return f;
  }

  /** @param args values in declaration order; a struct argument is passed as an array of values. */
  function calldata(sig, args) {
    var f = fn(sig);
    var flat = [];
    var types = [];
    (args || []).forEach(function (a, i) {
      var t = f.inputs[i];
      if (t.charAt(0) === "(") {
        // A static struct is inlined, so its fields are simply the next words.
        var inner = t.slice(1, -1).split(",");
        if (!Array.isArray(a) || a.length !== inner.length) {
          throw new Error("struct argument needs " + inner.length + " values");
        }
        inner.forEach(function (it, k) { types.push(it); flat.push(a[k]); });
      } else {
        types.push(t);
        flat.push(a);
      }
    });
    if (types.length !== flat.length) throw new Error("argument count");
    return f.sel + types.map(function (t, i) { return encodeOne(t, flat[i]); }).join("");
  }

  /** Decodes a return value against the generated output types. One value, or an array of them. */
  function returns(sig, data) {
    var f = fn(sig);
    var w = words(data);
    var types = [];
    f.outputs.forEach(function (t) {
      if (t.charAt(0) === "(") t.slice(1, -1).split(",").forEach(function (i) { types.push(i); });
      else types.push(t);
    });
    var out = types.map(function (t, i) { return decodeOne(t, w[i]); });
    return out.length === 1 ? out[0] : out;
  }

  /** Reads a returned static struct into an object, using the field names from the artifact. */
  function struct(name, data) {
    var fields = ABI.struct[name];
    var w = words(data);
    var out = {};
    fields.forEach(function (f, i) { out[f[0]] = decodeOne(f[1], w[i]); });
    return out;
  }

  // ------------------------------------------------------------------ errors

  /** Turns revert data into the vault's own vocabulary, so a refusal reads as a reason. */
  function revertReason(data) {
    var hex = strip(data);
    if (!hex) return null;
    var sel = "0x" + hex.slice(0, 8);
    if (ABI.err[sel]) return ABI.err[sel];
    // Error(string), the one standard revert the token contracts still use.
    if (sel === "0x08c379a0") {
      try {
        var len = Number(BigInt("0x" + hex.slice(8 + 64, 8 + 128)));
        var body = hex.slice(8 + 128, 8 + 128 + len * 2);
        return decodeURIComponent(body.replace(/../g, function (h) { return "%" + h; }));
      } catch (e) { return null; }
    }
    if (sel === "0x4e487b71") return "a panic inside the contract";
    return null;
  }

  /** Wallets bury the revert data at different depths. Look everywhere rather than guess. */
  function errorData(err) {
    var seen = [];
    var stack = [err];
    while (stack.length) {
      var e = stack.pop();
      if (!e || typeof e !== "object" || seen.indexOf(e) >= 0) continue;
      seen.push(e);
      if (typeof e.data === "string" && /^0x[0-9a-f]*$/i.test(e.data)) return e.data;
      ["data", "error", "cause", "originalError", "info"].forEach(function (k) {
        if (e[k] && typeof e[k] === "object") stack.push(e[k]);
      });
    }
    return null;
  }

  function explain(err) {
    var named = revertReason(errorData(err));
    if (named) return "The contract refused: " + named + ".";
    if (err && err.code === 4001) return null; // the wallet prompt was closed
    return (err && err.message) ? err.message : String(err);
  }

  // ------------------------------------------------------------------ transport

  var rpcId = 0;

  async function rpc(url, method, params) {
    var res = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: ++rpcId, method: method, params: params || [] })
    });
    var body = await res.json();
    if (body.error) {
      var e = new Error(body.error.message || "rpc error");
      e.code = body.error.code;
      e.data = body.error.data;
      throw e;
    }
    return body.result;
  }

  // ------------------------------------------------------------------ amounts

  /** Decimal string -> integer units. Written out because rounding a price is not a place for
      floating point, and the only alternative is a dependency. */
  function toUnits(text, decimals) {
    var t = String(text).trim();
    if (!/^\d*(\.\d*)?$/.test(t) || t === "" || t === ".") throw new Error("not a number: " + text);
    var parts = t.split(".");
    var frac = (parts[1] || "").slice(0, decimals);
    return BigInt((parts[0] || "0") + frac + "0".repeat(decimals - frac.length));
  }

  function fromUnits(value, decimals, places) {
    var n = BigInt(value);
    var base = 10n ** BigInt(decimals);
    var whole = n / base;
    var frac = (n % base).toString().padStart(decimals, "0");
    if (places === undefined) places = Math.min(decimals, 2);
    frac = frac.slice(0, places);
    var head = whole.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return places > 0 ? head + "." + frac : head;
  }

  return {
    calldata: calldata,
    returns: returns,
    struct: struct,
    words: words,
    decodeOne: decodeOne,
    encodeOne: encodeOne,
    revertReason: revertReason,
    explain: explain,
    rpc: rpc,
    toUnits: toUnits,
    fromUnits: fromUnits
  };
})();
