// eth.js encodes every transaction this page asks a wallet to sign, so it is held to the tool the
// rest of the repository treats as the reference: every expected value below is the output of
// `cast calldata` or `cast sig` for the same inputs, pasted in rather than recomputed here.
//
//   node --test app/test/
//
// No dependency. The scripts are loaded the way the browser loads them, into one shared global.

"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const APP = path.join(__dirname, "..");

function load() {
  const context = vm.createContext({ window: {}, BigInt, console });
  context.window = context;
  for (const name of ["abi.js", "eth.js"]) {
    vm.runInContext(fs.readFileSync(path.join(APP, name), "utf8"), context, { filename: name });
  }
  return context.Eth;
}

const Eth = load();

const LIST = "list(uint256,(uint128,uint128,uint128,uint32,uint32,uint32,uint16,uint8,address,uint128))";

test("list() calldata matches cast, byte for byte", () => {
  const terms = [65126020000n, 242400000n, 65126020000n, 604800n, 172800n, 604800n, 5000n, 0n,
                 "0x0000000000000000000000000000000000000000", 0n];
  assert.equal(Eth.calldata(LIST, [2989700n, terms]),
    "0x17763752" +
    "00000000000000000000000000000000000000000000000000000000002d9e84" +
    "0000000000000000000000000000000000000000000000000000000f29d033a0" +
    "000000000000000000000000000000000000000000000000000000000e72bb00" +
    "0000000000000000000000000000000000000000000000000000000f29d033a0" +
    "0000000000000000000000000000000000000000000000000000000000093a80" +
    "000000000000000000000000000000000000000000000000000000000002a300" +
    "0000000000000000000000000000000000000000000000000000000000093a80" +
    "0000000000000000000000000000000000000000000000000000000000001388" +
    "0000000000000000000000000000000000000000000000000000000000000000" +
    "0000000000000000000000000000000000000000000000000000000000000000" +
    "0000000000000000000000000000000000000000000000000000000000000000");
});

test("fund() and transferFinancierPosition() match cast", () => {
  assert.equal(Eth.calldata("fund(uint256)", [3n]),
    "0xca1d209d0000000000000000000000000000000000000000000000000000000000000003");
  assert.equal(
    Eth.calldata("transferFinancierPosition(uint256,address)", [7n, "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"]),
    "0x6470b9b0" +
    "0000000000000000000000000000000000000000000000000000000000000007" +
    "0000000000000000000000003c44cdddb6a900fa2b585dd299e03d12fa4293bc");
});

test("the token approve() the page builds by hand matches cast", () => {
  const encoded = "0x095ea7b3" +
    Eth.encodeOne("address", "0xab8eb9f37bd460df99b11767aa843a8f27fb7a6e") +
    Eth.encodeOne("uint256", 65126020000n);
  assert.equal(encoded,
    "0x095ea7b3" +
    "000000000000000000000000ab8eb9f37bd460df99b11767aa843a8f27fb7a6e" +
    "0000000000000000000000000000000000000000000000000000000f29d033a0");
});

test("a struct argument with the wrong number of fields is refused, not truncated", () => {
  assert.throws(() => Eth.calldata(LIST, [1n, [1n, 2n, 3n]]), /needs 10 values/);
});

test("the coder refuses what it cannot encode rather than guessing", () => {
  assert.throws(() => Eth.encodeOne("uint256", -1n), /negative/);
  assert.throws(() => Eth.encodeOne("address", "0x1234"), /not an address/);
  assert.throws(() => Eth.encodeOne("string", "x"), /static types/);
  assert.throws(() => Eth.encodeOne("uint256", 2n ** 256n), /wider than a word/);
});

test("a custom error comes back with its name", () => {
  assert.equal(Eth.revertReason("0x8fc8ee31"), "BuybackAboveSale");
  assert.match(Eth.explain({ data: "0x8fc8ee31" }), /refused: BuybackAboveSale/);
});

test("a standard Error(string) revert is decoded to its text", () => {
  const data = "0x08c379a0" +
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "0000000000000000000000000000000000000000000000000000000000000026" +
    "45524332303a207472616e7366657220616d6f756e7420657863656564732062" +
    "616c616e63650000000000000000000000000000000000000000000000000000";
  assert.equal(Eth.revertReason(data), "ERC20: transfer amount exceeds balance");
});

test("revert data buried inside a wallet error is still found", () => {
  const err = { message: "execution reverted", error: { data: { originalError: { data: "0x8fc8ee31" } } } };
  assert.match(Eth.explain(err), /BuybackAboveSale/);
});

test("closing the wallet prompt is not reported as a failure", () => {
  assert.equal(Eth.explain({ code: 4001, message: "User rejected" }), null);
});

test("amounts are parsed as decimals, never through a float", () => {
  assert.equal(Eth.toUnits("65126.02", 6), 65126020000n);
  assert.equal(Eth.toUnits("0.000001", 6), 1n);
  assert.equal(Eth.toUnits("1", 18), 10n ** 18n);
  // Precision beyond the token is cut, not rounded up into money that was never typed.
  assert.equal(Eth.toUnits("1.9999999", 6), 1999999n);
  // The float route would print 0.30000000000000004 here.
  assert.equal(Eth.toUnits("0.3", 6), 300000n);
  for (const bad of ["", ".", "1e5", "-1", "1,000", "abc", " "]) {
    assert.throws(() => Eth.toUnits(bad, 6), /not a number/, "accepted: " + JSON.stringify(bad));
  }
});

test("amounts are printed with separators and without losing units", () => {
  assert.equal(Eth.fromUnits(65126020000n, 6), "65,126.02");
  assert.equal(Eth.fromUnits(1n, 6, 6), "0.000001");
  assert.equal(Eth.fromUnits(0n, 6), "0.00");
  assert.equal(Eth.fromUnits(123456789012345678901234567890n, 18), "123,456,789,012.34");
});

test("a Deal is decoded field by field in the order the contract declares", () => {
  const words = [];
  const set = (i, hex) => { words[i] = hex.replace(/^0x/, "").padStart(64, "0"); };
  for (let i = 0; i < 22; i++) set(i, "0");
  set(0, "f39fd6e51aad88f6f4ce6ab8827279cfffb92266");   // seller
  set(2, (2989700).toString(16));                      // tokenId
  set(6, (65126020000).toString(16));                  // price
  set(19, "1");                                        // state: Listed
  const d = Eth.struct("Deal", "0x" + words.join(""));
  assert.equal(d.seller, "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266");
  assert.equal(d.tokenId, 2989700n);
  assert.equal(d.price, 65126020000n);
  assert.equal(d.state, 1n);
});
