"""Reads the waitlist collected before the signup form was removed, and prints it. Nothing is
written back.

The endpoint appends every signup and never checks for a duplicate on the way in: re-reading the
whole file per request is linear in its size, and the check-then-append it would need is a race
between concurrent requests anyway. So the de-duplication happens here, on the way out.

    railway ssh --service landing cat /data/waitlist.jsonl | python3 landing/read_waitlist.py
    railway ssh --service landing cat /data/waitlist.jsonl | python3 landing/read_waitlist.py --count
    python3 landing/read_waitlist.py --emails < some-local-copy.jsonl

The first signup for an address wins, so the timestamp shown is when that person actually joined
rather than the last time they hit the button.
"""

import json
import sys
import time


def read(stream):
    """Yields one record per address, oldest first."""
    seen, rows = set(), []
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            # A half-written last line is what an append-only file looks like mid-write. It is not
            # a reason to refuse to show the rest of the list.
            continue
        if not isinstance(record, dict):
            continue
        email = record.get("email")
        if not isinstance(email, str) or not email or email in seen:
            continue
        seen.add(email)
        rows.append(record)
    return rows


def main(argv):
    mode = argv[1] if len(argv) > 1 else ""
    rows = read(sys.stdin)

    if mode == "--count":
        print(len(rows))
        return 0
    if mode == "--emails":
        for record in rows:
            print(record["email"])
        return 0

    for record in rows:
        stamp = record.get("ts")
        when = time.strftime("%Y-%m-%d %H:%M", time.gmtime(stamp)) if isinstance(stamp, int) else "?"
        role = str(record.get("role", "?"))
        source = str(record.get("source", "?"))
        print("{}  {:<10} {:<8} {}".format(when, role, source, record["email"]))

    total = len(rows)
    print("\n{} on the list".format(total), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
