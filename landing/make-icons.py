"""The icon set, written once and emitted twice: as an inline <svg> sprite pasted into each landing
page (the landing runs no script and loads nothing it could avoid), and as one file per icon for the
docs site.

    python3 make-icons.py          rewrite both
    python3 make-icons.py --check  fail if either is stale

Stroke icons on a 24 grid, round caps, drawn to read at 20 to 28 px.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS_ICONS = os.path.join(HERE, os.pardir, "docs-site", "public", "icons")
PAGES = [os.path.join(HERE, "index.html"), os.path.join(HERE, "olanas.html"),
         os.path.join(HERE, os.pardir, "app", "index.html")]

ICONS = {
    "no-oracle": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/><path d="M4 4l16 16"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.4 8.3-8 9-4.6-.7-8-4-8-9V6l8-3z"/><path d="M8.5 12.2l2.4 2.4 4.6-4.8"/>',
    "no-fee": '<circle cx="7.5" cy="7.5" r="2.3"/><circle cx="16.5" cy="16.5" r="2.3"/><path d="M19 5L5 19"/>',
    "ceiling": '<path d="M4 5h16"/><path d="M12 20V9"/><path d="M8 13l4-4 4 4"/>',
    "tag": '<path d="M3 12.5V4a1 1 0 0 1 1-1h8.5L21 11.5 12.5 20 3 12.5z"/><circle cx="7.8" cy="7.8" r="1.6"/>',
    "key": '<circle cx="8" cy="15" r="4.2"/><path d="M11 12l9-9"/><path d="M16.5 6.5l3 3"/><path d="M14 9l2 2"/>',
    "buyback": '<path d="M20 12a8 8 0 1 1-2.35-5.65"/><path d="M20 4v5h-5"/>',
    "coins": '<path d="M12 3v18"/><path d="M16.5 7H10a3 3 0 0 0 0 6h4a3 3 0 0 1 0 6H7.5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
    "agent": '<rect x="4.5" y="7.5" width="15" height="12" rx="3.5"/><path d="M12 3.5v4"/><circle cx="12" cy="3" r="1"/><circle cx="9.5" cy="13" r="1.1"/><circle cx="14.5" cy="13" r="1.1"/><path d="M9.5 16.5h5"/>',
    "book": '<path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5z"/><path d="M5 19.5A1.5 1.5 0 0 0 6.5 21H19"/><path d="M9 7.5h6"/>',
    "code": '<path d="M8 7l-5 5 5 5"/><path d="M16 7l5 5-5 5"/><path d="M13.5 4l-3 16"/>',
    "chart": '<path d="M4 20h16"/><path d="M5 16l4.5-5.5 3.5 3 6-7.5"/><path d="M15 6h4v4"/>',
    "no-owner": '<circle cx="10" cy="8" r="3.5"/><path d="M3.5 20a6.5 6.5 0 0 1 13 0"/><path d="M17 5l4 4"/><path d="M21 5l-4 4"/>',
    "wallet": '<rect x="3" y="6" width="18" height="14" rx="3"/><path d="M3 10h13"/><path d="M16.5 14.5h1.5"/><path d="M7 6V4.5A1.5 1.5 0 0 1 8.5 3H17"/>',
    "flask": '<path d="M9 3h6"/><path d="M10 3v6.2L4.8 18a2 2 0 0 0 1.7 3h11a2 2 0 0 0 1.7-3L14 9.2V3"/><path d="M7.5 15h9"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.66 0l3-3A4 4 0 0 0 13 5.34l-1 1"/><path d="M14 10a4 4 0 0 0-5.66 0l-3 3A4 4 0 0 0 11 18.66l1-1"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
    "arrow": '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "spark": '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 17l.8 2.2L22 20l-2.2.8L19 23l-.8-2.2L16 20l2.2-.8z"/>',
    "github": '<path d="M9 19c-4 1.3-4-2-6-2.5M15 21v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.3 4.3 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12 12 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.3 4.3 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21"/>',
}

START, END = "<!-- icons:start -->", "<!-- icons:end -->"


def sprite():
    body = "\n".join('    <symbol id="i-%s" viewBox="0 0 24 24">%s</symbol>' % (k, v) for k, v in ICONS.items())
    return (START + '\n  <svg class="sprite" aria-hidden="true">\n'
            + body + "\n  </svg>\n  " + END)


def file_svg(paths):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#F5B84B" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">%s</svg>\n' % paths)


def main(check):
    stale = []
    for page in PAGES:
        text = open(page, encoding="utf-8").read()
        if START not in text:
            raise SystemExit("%s has no %s marker" % (page, START))
        new = re.sub(re.escape(START) + ".*?" + re.escape(END), lambda m: sprite(), text, flags=re.S)
        if new != text:
            stale.append(page)
            if not check:
                open(page, "w", encoding="utf-8", newline="\n").write(new)
    os.makedirs(DOCS_ICONS, exist_ok=True)
    for name, paths in ICONS.items():
        path = os.path.join(DOCS_ICONS, name + ".svg")
        want = file_svg(paths)
        have = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if have != want:
            stale.append(path)
            if not check:
                open(path, "w", encoding="utf-8", newline="\n").write(want)
    if check and stale:
        raise SystemExit("stale, run make-icons.py: " + ", ".join(os.path.basename(p) for p in stale))
    print("%d icons, %s" % (len(ICONS), "up to date" if check or not stale else "%d files written" % len(stale)))


if __name__ == "__main__":
    main("--check" in sys.argv)
