"""Generates app/abi.js from the compiled LeaseVault artifact.

    python make-abi-js.py            rewrite abi.js
    python make-abi-js.py --check    fail if abi.js is stale

The browser needs three things the Solidity source knows and a hand-written file would only
approximate: the selector of every function it calls, the exact order and width of every field in
`Deal`, and the selector of every custom error so a revert can be named instead of shown as hex.

All three are derived here from the artifact forge produced, so the page cannot drift from the
contract it is talking to. `check.sh` runs this with --check for the same reason it does for
openapi.json: the generated file is committed, and a committed generated file that nobody verifies
is just a stale file with a good reputation.

Standard library only, plus this repository's own keccak.
"""

import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "lp-api"))

from lpval.keccak import keccak256  # noqa: E402

ARTIFACT = os.path.join(ROOT, "lease-vault", "out", "LeaseVault.sol", "LeaseVault.json")
OUT = os.path.join(HERE, "abi.js")

# Everything the page calls on the vault. Naming them rather than emitting the whole ABI keeps the
# file readable and makes an accidental new entry point visible in a diff.
WANTED = [
    "dealCount", "deal", "accruedRent", "leaseEnd", "graceEnd", "balances", "positionOwed",
    "usdg", "posm", "stateView",
    "MIN_TERM", "MAX_TERM", "MIN_GRACE", "MAX_GRACE", "MAX_LISTING_DURATION",
    "MAX_FROZEN_BPS", "MAX_BUILDER_FEE_DIVISOR",
    "list", "cancel", "fund", "collectFees", "claimRent", "buyBack", "release",
    "transferFinancierPosition", "checkpointFreeze", "withdrawUSDG", "withdrawPosition",
]


def solidity_type(item):
    """The canonical type of one ABI input/output, with tuples expanded."""
    if item["type"].startswith("tuple"):
        inner = ",".join(solidity_type(c) for c in item["components"])
        return "(" + inner + ")" + item["type"][len("tuple"):]
    return item["type"]


def signature(entry):
    return entry["name"] + "(" + ",".join(solidity_type(i) for i in entry["inputs"]) + ")"


def selector(sig):
    return "0x" + keccak256(sig.encode()).hex()[:8]


def flatten(items):
    """Field names and types of a struct, in storage-free ABI order.

    Every field of `Deal` and `Terms` is a static type, which is why the page can read them as a
    flat run of 32-byte words. If that ever stops being true the generator says so here rather than
    letting the browser mis-decode a deal in silence.
    """
    out = []
    for i in items:
        t = solidity_type(i)
        if t.startswith("(") or t.endswith("]") or t in ("bytes", "string"):
            raise SystemExit("abi.js cannot carry a dynamic or nested field: %s %s" % (i["name"], t))
        out.append((i["name"], t))
    return out


def build():
    with io.open(ARTIFACT, encoding="utf-8") as fh:
        abi = json.load(fh)["abi"]

    fns, errs, structs = {}, {}, {}
    seen = set()

    for entry in abi:
        kind = entry.get("type")
        if kind == "error":
            errs[selector(signature(entry))] = entry["name"]
            continue
        if kind != "function" or entry["name"] not in WANTED:
            continue
        sig = signature(entry)
        seen.add(entry["name"])
        # `fund` is overloaded, so the key is the signature and the short name is an alias only
        # where it is unambiguous.
        fns[sig] = {
            "sel": selector(sig),
            "inputs": [solidity_type(i) for i in entry["inputs"]],
            "outputs": [solidity_type(o) for o in entry["outputs"]],
        }
        if entry["name"] == "deal" and entry["outputs"]:
            structs["Deal"] = flatten(entry["outputs"][0]["components"])
        if entry["name"] == "list":
            structs["Terms"] = flatten(entry["inputs"][1]["components"])

    missing = sorted(set(WANTED) - seen)
    if missing:
        raise SystemExit("the artifact has no such function: " + ", ".join(missing))

    return fns, errs, structs


def render(fns, errs, structs):
    """One entry per line. A generated file still gets read by people, and a diff that moves one
    selector should be one line long."""

    def q(s):
        return json.dumps(s)

    def compact(obj):
        return json.dumps(obj, separators=(", ", ": "))

    fn_lines = "\n".join(
        '    %s: { "sel": %s, "inputs": %s, "outputs": %s },'
        % (q(sig), q(d["sel"]), compact(d["inputs"]), compact(d["outputs"]))
        for sig, d in sorted(fns.items())
    )
    err_lines = "\n".join(
        "    %s: %s," % (q(sel), q(name)) for sel, name in sorted(errs.items(), key=lambda kv: kv[1])
    )
    struct_lines = "\n".join(
        "    %s: [\n%s\n    ]," % (q(name), "\n".join(
            "      [%s, %s]," % (q(f), q(t)) for f, t in fields))
        for name, fields in sorted(structs.items())
    )

    return (
        "/* Generated by make-abi-js.py from lease-vault/out/LeaseVault.sol/LeaseVault.json.\n"
        "   Do not edit: run `python make-abi-js.py` after changing the contract.\n"
        "   check.sh fails if this file and the compiled contract disagree. */\n\n"
        "window.TENURE_ABI = {\n"
        "  /* signature -> selector and argument types */\n"
        "  fn: {\n" + fn_lines + "\n  },\n\n"
        "  /* selector -> the name of the custom error the vault reverted with */\n"
        "  err: {\n" + err_lines + "\n  },\n\n"
        "  /* field order and width of the structs the page reads and writes, all static types */\n"
        "  struct: {\n" + struct_lines + "\n  },\n\n"
        "  /* Deal.state, in the order the enum declares it */\n"
        "  state: [\"None\", \"Listed\", \"Active\", \"BoughtBack\", \"Released\", \"Cancelled\"],\n\n"
        "  /* Selectors of the token calls the page makes, which are not on the vault.\n"
        "     Checked with `cast sig` rather than derived, because these contracts are not ours. */\n"
        "  token: {\n"
        "    \"approve(address,uint256)\": \"0x095ea7b3\",\n"
        "    \"allowance(address,address)\": \"0xdd62ed3e\",\n"
        "    \"balanceOf(address)\": \"0x70a08231\",\n"
        "    \"decimals()\": \"0x313ce567\",\n"
        "    \"symbol()\": \"0x95d89b41\",\n"
        "    \"getApproved(uint256)\": \"0x081812fc\",\n"
        "    \"ownerOf(uint256)\": \"0x6352211e\"\n"
        "  }\n"
        "};\n"
    )


if __name__ == "__main__":
    if not os.path.exists(ARTIFACT):
        raise SystemExit("no artifact at %s -- run `forge build` in lease-vault first" % ARTIFACT)

    text = render(*build())

    if "--check" in sys.argv:
        if not os.path.exists(OUT):
            raise SystemExit("abi.js does not exist")
        with io.open(OUT, encoding="utf-8") as fh:
            if fh.read() != text:
                raise SystemExit("abi.js is stale -- run `python app/make-abi-js.py`")
        print("   abi.js matches the compiled contract")
    else:
        with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print("wrote %s" % OUT)
