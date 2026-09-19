#!/usr/bin/env python3
"""Generates every brand asset from one place. Text is converted to outlines, so the SVGs render
identically everywhere and need no font installed.

    python3 build.py            # uses NAME below
    python3 build.py Acme       # try another name

Requires fontTools and a copy of Bahnschrift (ships with Windows 10/11).
"""
import math
import os
import sys

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

NAME = sys.argv[1] if len(sys.argv) > 1 else "Tenure"
TAGLINE = "SALE · LEASE · BUY BACK"
HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.environ.get("BRAND_FONT", "/mnt/c/Windows/Fonts/bahnschrift.ttf")

NAVY, NAVY_HI, NAVY_LO = "#0E1726", "#1B2B48", "#0A111D"
INK, AMBER, AMBER_HI, AMBER_LO, AMBER_DARK = "#F4F1EA", "#F5B84B", "#FFD683", "#EFA233", "#A96F0C"
MUTED = "#2A3C60"

# ---------------------------------------------------------------------------- type

_fonts = {}
KERN = {("T", "e"): -0.085, ("T", "a"): -0.085, ("T", "o"): -0.085, ("r", "e"): -0.01}


def font(weight):
    if weight not in _fonts:
        _fonts[weight] = instancer.instantiateVariableFont(TTFont(FONT), {"wght": weight, "wdth": 100})
    return _fonts[weight]


def text(s, size, x, y, weight=600, tracking=0.0, fill=INK, anchor="start", opacity=None):
    """Returns (svg_path_element, rendered_width). Tracking and kerning are in em."""
    f = font(weight)
    glyphs, cmap, upm = f.getGlyphSet(), f.getBestCmap(), f["head"].unitsPerEm
    pen, adv = SVGPathPen(glyphs), 0.0
    for i, ch in enumerate(s):
        if i:
            adv += (KERN.get((s[i - 1], ch), 0.0) + tracking) * upm
        g = glyphs[cmap[ord(ch)]]
        g.draw(TransformPen(pen, (1, 0, 0, 1, adv, 0)))
        adv += g.width
    k = size / upm
    width = adv * k
    if anchor == "end":
        x -= width
    elif anchor == "middle":
        x -= width / 2
    op = f' opacity="{opacity}"' if opacity is not None else ""
    el = f'<path fill="{fill}"{op} transform="translate({x:.2f} {y:.2f}) scale({k:.5f} {-k:.5f})" d="{pen.getCommands()}"/>'
    return el, width


# ---------------------------------------------------------------------------- mark

def geometry(small=False):
    """All measurements of the symbol in a 512 box. `small` is the heavier cut for 32 px and below.

    Construction: two range bounds; between them the liquidity curve, a true bell with flat tails and
    a round crown; on its crown the current price. The curve stops short of the bounds by exactly one
    stroke radius, so nothing touches.
    """
    bar_w, stroke, dot = (44, 46, 0) if small else (28, 30, 19)
    left, right = (70, 442) if small else (82, 430)  # outer edges of the two bounds
    top, bottom = 112, 400
    base_y, peak_y = (338, 196) if small else (352, 190)
    gap = stroke / 2 + (10 if small else 14)
    x0, x1 = left + bar_w + gap, right - bar_w - gap
    half = (x1 - x0) / 2
    c_tail, c_top = 0.50 * half, 0.60 * half  # flat tails, round crown
    # The price sits on the right flank of the curve, not on its crown: a centred dot reads as a head.
    t = 0.40
    bx = [256, 256 + c_top, x1 - c_tail, x1]
    by = [peak_y, peak_y, base_y, base_y]
    w = [(1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3]
    px, py = sum(a * b for a, b in zip(w, bx)), sum(a * b for a, b in zip(w, by))
    curve = (
        f"M{x0:.1f} {base_y} C {x0 + c_tail:.1f} {base_y} {256 - c_top:.1f} {peak_y} 256 {peak_y} "
        f"S {x1 - c_tail:.1f} {base_y} {x1:.1f} {base_y}"
    )
    return dict(bar_w=bar_w, stroke=stroke, dot=dot, halo=dot + 12, px=round(px, 1), py=round(py, 1), left=left,
                right=right, top=top, bottom=bottom, base_y=base_y, peak_y=peak_y, curve=curve)


def defs(uid):
    return f"""
    <radialGradient id="bg{uid}" cx="256" cy="190" r="400" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{NAVY_HI}"/><stop offset="0.6" stop-color="{NAVY}"/><stop offset="1" stop-color="{NAVY_LO}"/>
    </radialGradient>
    <linearGradient id="am{uid}" x1="0" y1="160" x2="0" y2="360" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{AMBER_HI}"/><stop offset="0.5" stop-color="{AMBER}"/><stop offset="1" stop-color="{AMBER_LO}"/>
    </linearGradient>
    <linearGradient id="gl{uid}" x1="0" y1="190" x2="0" y2="352" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{AMBER}" stop-opacity="0.34"/><stop offset="1" stop-color="{AMBER}" stop-opacity="0.04"/>
    </linearGradient>
    <clipPath id="tile{uid}"><rect width="512" height="512" rx="116"/></clipPath>"""


def mark(uid="", outline=False, small=False, content_scale=1.0):
    """The symbol on its navy tile, in a 512 box.

    `content_scale` shrinks the drawing about the centre while the tile stays full-bleed: used for
    the avatar, where a circular crop eats the corners.
    """
    g = geometry(small)
    h = g["bottom"] - g["top"]
    o = f'<g transform="translate(256 256) scale({content_scale}) translate(-256 -256)">' if content_scale != 1 else ""
    c = "</g>" if content_scale != 1 else ""
    ring = f'<rect x="1.5" y="1.5" width="509" height="509" rx="114.5" fill="none" stroke="{INK}" stroke-opacity="0.10" stroke-width="3"/>'
    glow = "" if small else f'<path d="{g["curve"]} Z" fill="url(#gl{uid})"/>'
    price = "" if small else (
        f'<circle cx="{g["px"]}" cy="{g["py"]}" r="{g["halo"]}" fill="{NAVY}"/>'
        f'<circle cx="{g["px"]}" cy="{g["py"]}" r="{g["dot"]}" fill="{INK}"/>'
    )
    return f"""
    <g clip-path="url(#tile{uid})">
      <rect width="512" height="512" fill="url(#bg{uid})"/>
      {o}{glow}
      <path d="{g["curve"]}" fill="none" stroke="url(#am{uid})" stroke-width="{g["stroke"]}" stroke-linecap="round"/>
      <rect x="{g["left"]}" y="{g["top"]}" width="{g["bar_w"]}" height="{h}" rx="{g["bar_w"] / 2}" fill="{INK}"/>
      <rect x="{g["right"] - g["bar_w"]}" y="{g["top"]}" width="{g["bar_w"]}" height="{h}" rx="{g["bar_w"] / 2}" fill="{INK}"/>
      {price}{c}
    </g>{ring if outline else ""}"""


def mark_mono(color="currentColor"):
    """One-colour version, no tile: stamps, embossing, watermarks. The price is a true cut-out."""
    g = geometry()
    h = g["bottom"] - g["top"]
    uid = "k" + color.strip("#")
    return f"""
    <mask id="{uid}" maskUnits="userSpaceOnUse" x="0" y="0" width="512" height="512">
      <rect width="512" height="512" fill="#fff"/><circle cx="{g["px"]}" cy="{g["py"]}" r="{g["halo"]}" fill="#000"/>
    </mask>
    <path d="{g["curve"]}" fill="none" stroke="{color}" stroke-width="{g["stroke"]}" stroke-linecap="round" mask="url(#{uid})"/>
    <circle cx="{g["px"]}" cy="{g["py"]}" r="{g["dot"]}" fill="{color}"/>
    <rect x="{g["left"]}" y="{g["top"]}" width="{g["bar_w"]}" height="{h}" rx="{g["bar_w"] / 2}" fill="{color}"/>
    <rect x="{g["right"] - g["bar_w"]}" y="{g["top"]}" width="{g["bar_w"]}" height="{h}" rx="{g["bar_w"] / 2}" fill="{color}"/>"""


def svg(w, h, body, extra_defs=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
        f'aria-label="{NAME}">\n  <defs>{extra_defs}\n  </defs>{body}\n</svg>\n'
    )


def write(name, content):
    with open(os.path.join(HERE, name), "w", encoding="utf-8") as fh:
        fh.write(content)
    print("wrote", name)


# ---------------------------------------------------------------------------- assets

def build_mark():
    write("logo-mark.svg", svg(512, 512, mark(), defs("")))
    write("logo-mark-small.svg", svg(512, 512, mark(small=True), defs("")))  # favicon, 32 px and below
    write("logo-mark-mono.svg", svg(512, 512, mark_mono("#0E1726")))
    # Profile picture: X, Discord and Telegram all crop to a circle, so the drawing is pulled inside
    # the inscribed circle and the tile is left full-bleed.
    write("logo-avatar.svg", svg(512, 512, mark("A", content_scale=0.84), defs("A")))


def build_lockup(theme):
    dark = theme == "dark"
    bg, ink, accent = (NAVY, INK, AMBER) if dark else (INK, NAVY, AMBER_DARK)
    word, w_word = text(NAME, 176, 352, 236, weight=600, tracking=-0.012, fill=ink)
    tag, _ = text(TAGLINE, 25, 357, 292, weight=500, tracking=0.24, fill=accent)
    width = max(1200, int(352 + w_word + 96))
    body = f"""
  <rect width="{width}" height="400" fill="{bg}"/>
  <g transform="translate(88 88) scale(0.4375)">{mark("L", outline=dark)}
  </g>
  {word}
  {tag}"""
    write(f"logo-horizontal-{theme}.svg", svg(width, 400, body, defs("L")))


def build_nav_lockup():
    """Tight, transparent lockup for website headers: symbol tile plus wordmark, nothing else."""
    word, w_word = text(NAME, 46, 78, 47, weight=600, tracking=-0.012, fill=INK)
    width = int(78 + w_word + 2)
    body = f"""
  <g transform="scale(0.125)">{mark("N", outline=True)}
  </g>
  {word}"""
    write("logo-nav.svg", svg(width, 64, body, defs("N")))


# ---------------------------------------------------------------------------- banner
#
# The chart is the original drawing, kept as it was. Only the typography changes between the
# treatments below, and t2/t3 slide the chart right so the phrase has room to grow.

def banner_chart(uid, dx=0):
    """The liquidity chart: bell curve, lit range, the two bounds, the price on the right flank."""
    W, H = 1500, 500
    curve = (f"M{560 + dx} 466 C {830 + dx} 466 {930 + dx} 118 {1070 + dx} 118 "
             f"S {1290 + dx} 466 {1500 + dx} 432")
    # Price at a quarter along the curve's second segment, as in the logo.
    t, bx, by = 0.25, [1070 + dx, 1210 + dx, 1290 + dx, 1500 + dx], [118, 118, 466, 432]
    w = [(1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3]
    px, py = sum(p * q for p, q in zip(w, bx)), sum(p * q for p, q in zip(w, by))
    lo, hi = 899 + dx, 1229 + dx
    l1, _ = text("TICK LOWER", 15, lo + 6, 76, weight=600, tracking=0.2, opacity=0.5, anchor="middle")
    l2, _ = text("TICK UPPER", 15, hi + 6, 76, weight=600, tracking=0.2, opacity=0.5, anchor="middle")
    l3, _ = text("PRICE", 15, px + 4, py - 34, weight=600, tracking=0.2, fill=AMBER, anchor="middle")
    extra = f"""
    <linearGradient id="bbg{uid}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{NAVY_LO}"/><stop offset="0.5" stop-color="{NAVY}"/><stop offset="1" stop-color="{NAVY_HI}"/>
    </linearGradient>
    <linearGradient id="bfill{uid}" x1="0" y1="118" x2="0" y2="466" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{AMBER}" stop-opacity="0.42"/><stop offset="1" stop-color="{AMBER}" stop-opacity="0.02"/>
    </linearGradient>
    <pattern id="ticks{uid}" width="30" height="{H}" patternUnits="userSpaceOnUse">
      <rect x="0" y="454" width="2" height="12" fill="{INK}" opacity="0.14"/>
    </pattern>
    <clipPath id="brange{uid}"><rect x="{917 + dx}" y="0" width="306" height="{H}"/></clipPath>"""
    body = f"""
  <rect width="{W}" height="{H}" fill="url(#bbg{uid})"/>
  <rect width="{W}" height="{H}" fill="url(#ticks{uid})"/>
  <rect x="0" y="466" width="{W}" height="2" fill="{INK}" opacity="0.14"/>
  <path d="{curve} L{1500 + dx} 466 Z" fill="{INK}" opacity="0.045"/>
  <path d="{curve} L{1500 + dx} 466 Z" fill="url(#bfill{uid})" clip-path="url(#brange{uid})"/>
  <path d="{curve}" fill="none" stroke="{INK}" stroke-width="2.5" opacity="0.26"/>
  <path d="{curve}" fill="none" stroke="{AMBER}" stroke-width="5" stroke-linecap="round" clip-path="url(#brange{uid})"/>
  <rect x="{lo}" y="96" width="12" height="372" rx="6" fill="{INK}"/>
  <rect x="{hi}" y="96" width="12" height="372" rx="6" fill="{INK}"/>
  <circle cx="{px:.1f}" cy="{py:.1f}" r="17" fill="{NAVY}"/>
  <circle cx="{px:.1f}" cy="{py:.1f}" r="10" fill="{INK}"/>
  {l1}
  {l2}
  {l3}"""
    return body, extra, lo


def banner_logo(uid):
    word, _ = text(NAME, 36, 128, 96, weight=600, tracking=-0.012)
    return f'<g transform="translate(72 60) scale(0.0859)">{mark(uid, outline=True)}</g>\n  {word}'


def phrase(size, x, ys, tracking=-0.018, accent_word=False):
    """The three lines. With accent_word only the last word is amber, not the whole line."""
    parts, widest = [], 0.0
    rows = [("Sell it.", INK), ("Lease it back.", INK), ("Keep the fees.", INK if accent_word else AMBER)]
    for (s, fill), y in zip(rows, ys):
        if accent_word and s.startswith("Keep"):
            head, tail = "Keep the ", "fees."
            el, w = text(head, size, x, y, weight=700, tracking=tracking, fill=INK)
            el2, w2 = text(tail, size, x + w + size * tracking, y, weight=700, tracking=tracking, fill=AMBER)
            parts += [el, el2]
            widest = max(widest, w + w2)
        else:
            el, w = text(s, size, x, y, weight=700, tracking=tracking, fill=fill)
            parts.append(el)
            widest = max(widest, w)
    return "".join(parts), x + widest


def build_banner_t(key):
    """t1: the original chart untouched, phrase re-set. t2: phrase grown, chart slid right.
    t3: t2 plus an eyebrow above the phrase."""
    uid = "T" + key[-1]
    dx = 0 if key == "t1" else 110
    chart, extra, lo = banner_chart(uid, dx)
    head = ""
    if key == "t1":
        block, right = phrase(64, 408, [196, 266, 336])
    elif key == "t2":
        block, right = phrase(78, 400, [186, 270, 354])
    else:
        head, _ = text("UNISWAP V4 · ROBINHOOD CHAIN", 17, 410, 152, weight=600, tracking=0.2, fill=AMBER)
        block, right = phrase(78, 408, [200, 284, 368])
    assert right < lo - 20, f"{key}: the phrase runs into the chart ({right:.0f} vs {lo})"
    body = f"{chart}\n  {banner_logo(uid)}\n  {head}\n  {block}"
    write(f"banner-{key}.svg", svg(1500, 500, body, defs(uid) + extra))


def build_banner():
    """The active header. BRAND_BANNER picks the text treatment: t1, t2 or t3."""
    choice = os.environ.get("BRAND_BANNER", "t2").lower()
    with open(os.path.join(HERE, f"banner-{choice}.svg"), encoding="utf-8") as fh:
        write("banner-1500x500.svg", fh.read())


def build_sheet():
    """Control sheet: the mark at small sizes on dark and light, plus the mono version."""
    sizes, x, parts = [256, 128, 64, 32, 16], 40, []
    for row, bgc in enumerate([NAVY_LO, INK]):
        y0 = 40 + row * 330
        parts.append(f'<rect x="0" y="{row * 330}" width="1000" height="330" fill="{bgc}"/>')
        x = 40
        for i, s in enumerate(sizes):
            uid = f"S{row}{i}"
            parts.append(f"<defs>{defs(uid)}</defs>")
            parts.append(
                f'<g transform="translate({x} {y0}) scale({s / 512:.5f})">{mark(uid, outline=row == 0, small=s <= 32)}</g>'
            )
            x += s + 36
        col = INK if row == 0 else NAVY
        parts.append(f'<g transform="translate({x + 20} {y0}) scale(0.5)">{mark_mono(col)}</g>')
    write("_sheet.svg", svg(1000, 660, "\n  ".join(parts)))


if __name__ == "__main__":
    build_mark()
    build_lockup("dark")
    build_lockup("light")
    build_nav_lockup()
    for k in ("t1", "t2", "t3"):
        build_banner_t(k)
    build_banner()
    build_sheet()
