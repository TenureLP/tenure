"""Updates the launchpad listing in place, without republishing it.

    python olanas-listing.py show      what is live now
    python olanas-listing.py update    opens a local page, signs with the creator wallet, sends it
    python olanas-listing.py plan      prints the message, for signing by some other means
    python olanas-listing.py send --timestamp T --signature 0x...

The launchpad lets the creator change a listing's name, description, video link, price, status,
endpoint and methods, each authorised by a signature from the creator wallet. It does **not** let
anyone change the OpenAPI document, the logo or the category: those exist only as they were at
creation. Replacing them would mean deleting the service and creating it again, which mints a new
serviceId and a new createdAt, and the createdAt is the only evidence of having been first.

So the copy below is the listing, and it lives here rather than in a form, where a diff shows what
changed and when.

Standard library only. The private key never comes near this script: `plan` prints a message,
something else signs it, `send` carries the signature.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import OrderedDict

import olanas_sign

LAUNCHPAD = "https://olanas.xyz"
SLUG = "tenure-position-valuation"

# What the listing should say. An agent reads `name` when it searches, and `description` when it
# decides, so the first names the job and the second says what is actually answered and what is
# refused.
NAME = "Tenure: manage a Uniswap v4 LP position with an agent"

DESCRIPTION = (
    "Give an agent the id of a Uniswap v4 position on Robinhood Chain and it can answer the "
    "questions a liquidity provider actually has. What the position holds right now. Whether its "
    "range is still around the price, or has stopped earning. What it really earned over a full "
    "day of chain history, read from the pool's own fee accumulators rather than modelled. And "
    "what it could be sold and leased back for, so the position can raise cash without being "
    "given up.\n\n"
    "Every figure is exact integer arithmetic, with no floating point anywhere a number is "
    "derived. Positions that are empty, out of range, or sitting on a fee counter that has "
    "wrapped around are refused rather than guessed at, and the refusal says which.\n\n"
    "It reads the chain and nothing else. It never signs, moves or rebalances anything, and it "
    "never asks for a key."
)

# Only the keys the launchpad accepts, in the order it inserts them, because the signature covers
# the object it builds rather than the one sent.
FIELD_ORDER = ["name", "description", "videoUrl", "status", "price", "endpointUrl", "allowedMethods"]

CHANGES = {"name": NAME, "description": DESCRIPTION}


def normalise(changes):
    """Mirrors what the launchpad does to the requested changes before it verifies the signature.

    Anything that does not survive this unchanged would produce a signature over a different
    object than the one the server checks, and the request would be refused as a mismatch.
    """
    out = OrderedDict()
    for key in FIELD_ORDER:
        if key not in changes:
            continue
        value = changes[key]
        if key in ("name", "description", "videoUrl"):
            value = str(value).strip()
        elif key == "allowedMethods":
            value = sorted({str(m).upper() for m in value})
        else:
            value = str(value)
        out[key] = value

    if "name" in out and not 0 < len(out["name"]) <= 120:
        raise SystemExit("a name is 1 to 120 characters, this one is %d" % len(out["name"]))
    if "description" in out and len(out["description"]) > 2000:
        raise SystemExit("a description is at most 2000 characters, this one is %d" % len(out["description"]))
    if "status" in out and out["status"] not in ("live", "paused"):
        raise SystemExit("status is live or paused")
    return out


def message(action, changes, timestamp):
    """The exact bytes to sign.

    JSON.stringify writes no spaces, keeps insertion order and leaves non-ASCII characters as they
    are. The first two are matched here; the third is why the copy above is kept ASCII, since a
    single curly quote encoded differently on the two sides is a signature that verifies to a
    stranger's address and an error message that explains nothing.
    """
    body = OrderedDict([("action", action), ("slug", SLUG), ("changes", changes),
                        ("timestamp", timestamp)])
    text = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    if not text.isascii():
        raise SystemExit("the changes contain non-ASCII characters; keep the copy plain")
    return "x402 manage service\n" + text


def get(path):
    with urllib.request.urlopen(LAUNCHPAD + path, timeout=20) as r:
        return json.loads(r.read().decode())


def show():
    service = get("/api/services/" + SLUG)["service"]
    for key in ("name", "status", "price", "currency", "allowedMethods", "requests", "revenue",
                "creatorAddress", "createdAt", "updatedAt"):
        print("  %-16s %s" % (key, service.get(key)))
    print()
    print("  description")
    for line in str(service.get("description", "")).splitlines() or [""]:
        print("    " + line)
    return service


def plan(timestamp=None):
    service = get("/api/services/" + SLUG)["service"]
    changes = normalise(CHANGES)

    same = [k for k, v in changes.items() if service.get(k) == v]
    if len(same) == len(changes):
        print("  the listing already says all of this; nothing to send")
        return None
    for key in changes:
        print("  %-12s %s" % (key, "unchanged" if key in same else "will change"))

    timestamp = timestamp or str(int(time.time() * 1000))
    print()
    print("  creator wallet   %s" % service["creatorAddress"])
    print("  timestamp        %s   (valid for five minutes)" % timestamp)
    print()
    print("  Sign this exactly, as a personal_sign message:")
    print()
    print(message("update", changes, timestamp))
    print()
    print("  Then, within five minutes:")
    print("    python olanas-listing.py send --timestamp %s --signature 0x..." % timestamp)
    return timestamp


def patch(timestamp, signature):
    """Sends the change. Raises with whatever the launchpad said, which is worth reading: it
    distinguishes an expired signature from a mismatched one from a reused one."""
    changes = normalise(CHANGES)
    payload = {"changes": changes, "creatorTimestamp": timestamp, "creatorSignature": signature}
    request = urllib.request.Request(
        LAUNCHPAD + "/api/services/" + SLUG,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as r:
            body = json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("error", detail)
        except ValueError:
            pass
        raise RuntimeError("HTTP %d: %s" % (exc.code, detail))
    return {"name": body["service"]["name"], "updatedAt": body["service"]["updatedAt"]}


def send(timestamp, signature):
    answer = patch(timestamp, signature)
    print("  updated")
    print("  name        %s" % answer["name"])
    print("  updatedAt   %s" % answer["updatedAt"])


def update():
    """The whole thing: page, wallet, signature, PATCH."""
    service = get("/api/services/" + SLUG)["service"]
    changes = normalise(CHANGES)
    if all(service.get(k) == v for k, v in changes.items()):
        print("  the listing already says all of this; nothing to send")
        return
    answer = olanas_sign.run(
        creator=service["creatorAddress"],
        changes=changes,
        build_message=lambda ts: message("update", changes, ts),
        patch=patch,
    )
    if answer:
        print("  updated")
        print("  name        %s" % answer["name"])
        print("  updatedAt   %s" % answer["updatedAt"])
    else:
        print("  nothing was signed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("show", "plan", "update", "send"))
    parser.add_argument("--timestamp")
    parser.add_argument("--signature")
    args = parser.parse_args()

    if args.action == "show":
        show()
    elif args.action == "plan":
        plan(args.timestamp)
    elif args.action == "update":
        update()
    else:
        if not args.timestamp or not args.signature:
            raise SystemExit("send needs the --timestamp that was signed and the --signature")
        send(args.timestamp, args.signature)
    sys.exit(0)
