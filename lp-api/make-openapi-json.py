"""Regenerates openapi.json from openapi.yaml.

    python3 make-openapi-json.py        writes openapi.json
    python3 make-openapi-json.py --check  exits non-zero if it is stale

The document is authored in YAML because that is the version people read: it carries the comments
and the prose. The JSON is what tooling asks for, and some of it will not take anything else.

This needs PyYAML, which the service itself does not: the conversion happens here, at development
time, and the result is committed like the rendered brand images are. Nothing at runtime gains a
dependency.
"""

import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "openapi.yaml")
OUT = os.path.join(HERE, "openapi.json")


def build():
    import yaml  # noqa: PLC0415  development-time only, deliberately not a runtime import

    with io.open(SRC, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    # Sorted keys would scramble the reading order of paths and parameters for no gain; the file is
    # generated, so a stable serialiser is all the determinism it needs.
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def main(argv):
    text = build()
    if "--check" in argv:
        try:
            with io.open(OUT, encoding="utf-8") as fh:
                current = fh.read()
        except OSError:
            print("openapi.json is missing; run make-openapi-json.py", file=sys.stderr)
            return 1
        if current != text:
            print("openapi.json is stale; run make-openapi-json.py", file=sys.stderr)
            return 1
        print("   openapi.json matches openapi.yaml")
        return 0

    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("wrote openapi.json, %d bytes" % len(text.encode("utf-8")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
