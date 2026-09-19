"""Builds the post cards as 1600x900 HTML, one file each, from one stylesheet.

    python3 cards.py            writes card-*.html next to this file
    ./render-cards.ps1          rasterises them with headless Chrome

Eight of the fifteen posts carry a card. The other seven read better as plain text: an image on
every post looks like a content mill, and X does not reward it. A card earns its place only where
the drawing shows the mechanism better than the sentence does.

Every figure here is real. Card 3 in particular is a live position and goes stale: re-run
`lp-api/run.sh position 2908254 --quote` and update POSITION below before posting it.
"""

import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# A live position, read on 19 September 2026. Refresh before posting card 3.
POSITION = {
    "id": "2908254",
    "value": "488.96",
    "feesPerDay": "34.58",
    "sale": "391.17",
    "buyback": "391.17",
    "rent": "121.04",
    "apr": "2,725",
}

CSS = """
  :root {
    --navy-lo:#0A111D; --navy:#0E1726; --navy-hi:#1B2B48; --panel:#121D31;
    --ink:#F4F1EA; --amber:#F5B84B; --amber-hi:#FFD683;
    --muted:rgba(244,241,234,.58); --faint:rgba(244,241,234,.34);
    --line:rgba(244,241,234,.11); --line-hi:rgba(244,241,234,.20);
    --green:#7BE0A6; --dim:rgba(244,241,234,.28);
  }
  * { box-sizing:border-box; margin:0 }
  html,body { width:1600px; height:900px; overflow:hidden }
  body {
    background: radial-gradient(1100px 700px at 78% 18%, rgba(27,43,72,.85), transparent 70%),
                linear-gradient(158deg, var(--navy-lo), var(--navy) 58%, #13203a);
    color: var(--ink);
    font-family: Bahnschrift, "DIN Alternate", "Segoe UI", sans-serif;
    -webkit-font-smoothing: antialiased;
    padding: 58px 66px;
    display:flex; flex-direction:column;
  }
  .top { display:flex; align-items:center; justify-content:space-between; margin-bottom:38px; flex:none }
  .brand { display:flex; align-items:center; gap:16px; font-size:33px; font-weight:600; letter-spacing:-.01em }
  .brand svg { width:50px; height:50px }
  .tag { font-size:16px; font-weight:600; letter-spacing:.2em; color:var(--amber) }

  h1 { font-size:54px; font-weight:700; letter-spacing:-.02em; line-height:1.06; margin-bottom:12px }
  h1 b { color:var(--amber); font-weight:700 }
  .sub { font-size:23px; color:var(--muted); margin-bottom:36px; max-width:1180px; line-height:1.35 }

  .grow { flex:1; display:flex; flex-direction:column; justify-content:center }
  .foot { flex:none; margin-top:36px; padding-top:22px; border-top:1px solid var(--line);
          font-size:21px; color:var(--muted) }
  .foot b { color:var(--ink); font-weight:600 }

  .panel { background:var(--panel); border:1px solid var(--line); border-radius:18px; padding:26px 30px }
  .mono { font-family: Consolas, "SF Mono", Menlo, monospace }
  .eyebrow { font-size:14px; font-weight:600; letter-spacing:.2em; color:var(--faint); margin-bottom:14px }
"""

MARK = (
    '<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">'
    '<rect x="4" y="30" width="11" height="30" rx="2.5" fill="#F5B84B"/>'
    '<rect x="19.5" y="18" width="11" height="42" rx="2.5" fill="#F5B84B" opacity=".72"/>'
    '<rect x="35" y="8" width="11" height="52" rx="2.5" fill="#F5B84B" opacity=".46"/>'
    '<rect x="50.5" y="24" width="11" height="36" rx="2.5" fill="#F5B84B" opacity=".26"/>'
    "</svg>"
)


def page(tag, body, extra=""):
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<title>Tenure card</title>\n<style>" + CSS + extra + "</style>\n</head>\n<body>\n"
        '<div class="top"><div class="brand">' + MARK + "<span>Tenure</span></div>"
        '<div class="tag">' + tag + "</div></div>\n" + body + "\n</body>\n</html>\n"
    )


# ---------------------------------------------------------------------- 1, the three acts

CARD1 = page(
    "HOW IT WORKS",
    """
<h1>Sell it. Lease it back. <b>Keep the fees.</b></h1>
<div class="sub">Three acts, one transaction each. No debt is created at any point.</div>
<div class="grow">
  <div class="acts">
    <div class="act">
      <div class="n">01 &nbsp; SALE</div>
      <div class="t">The position NFT goes to the financier. You are paid the price, less the
        prepaid rent.</div>
    </div>
    <div class="arrow">&rarr;</div>
    <div class="act">
      <div class="n">02 &nbsp; LEASE</div>
      <div class="t">You keep collecting the pool's swap fees, as often as you like, against a
        fixed rent. Liquidity is untouchable.</div>
    </div>
    <div class="arrow">&rarr;</div>
    <div class="act">
      <div class="n">03 &nbsp; BUYBACK</div>
      <div class="t">You buy it back at a price agreed upfront. Or you do not, and the financier
        keeps what they already own.</div>
    </div>
  </div>
</div>
<div class="foot"><b>No loan. No liquidation. No oracle.</b> There is nothing to seize, because
  nothing was lent.</div>
""",
    """
  .acts { display:flex; align-items:stretch; gap:18px }
  .act { flex:1; background:var(--panel); border:1px solid var(--line); border-radius:18px;
         padding:28px 30px; display:flex; flex-direction:column; gap:14px }
  .act .n { font-size:15px; font-weight:600; letter-spacing:.18em; color:var(--amber) }
  .act .t { font-size:24px; line-height:1.34; color:var(--ink) }
  .arrow { display:flex; align-items:center; font-size:34px; color:var(--dim); flex:none }
""",
)

# ---------------------------------------------------------------------- 2, loan versus lease

ROWS = [
    ("Creates debt", "A sale, a lease, a promise"),
    ("Needs a price feed", "Reads a price exactly never"),
    ("Has a liquidation price", "Has none"),
    ("Your position can be seized", "The financier keeps what they own"),
]

CARD2 = page(
    "NOT A LOAN",
    """
<h1>Same cash today. <b>A different contract.</b></h1>
<div class="sub">Borrowing against a liquidity position and selling it are not the same act, and
  the difference is not cosmetic.</div>
<div class="grow">
  <div class="cmp">
    <div class="col">
      <div class="head dim">Borrowing against your LP</div>
      """
    + "".join('<div class="row dim">%s</div>' % a for a, _ in ROWS)
    + """
    </div>
    <div class="col lit">
      <div class="head">Tenure</div>
      """
    + "".join('<div class="row">%s</div>' % b for _, b in ROWS)
    + """
    </div>
  </div>
</div>
<div class="foot">Debt needs a feed, and a feed has to be right at the exact moment somebody
  reads it. <b>This one reads no price at all.</b></div>
""",
    """
  .cmp { display:grid; grid-template-columns:1fr 1fr; gap:20px }
  .col { background:var(--panel); border:1px solid var(--line); border-radius:18px; overflow:hidden }
  .col.lit { border-color:rgba(245,184,75,.45); background:linear-gradient(180deg,rgba(245,184,75,.07),var(--panel) 60%) }
  .head { font-size:17px; font-weight:600; letter-spacing:.16em; padding:20px 28px;
          border-bottom:1px solid var(--line); color:var(--amber) }
  .head.dim { color:var(--faint) }
  .row { font-size:24px; padding:20px 28px; border-bottom:1px solid var(--line); line-height:1.3 }
  .row:last-child { border-bottom:none }
  .row.dim { color:var(--muted) }
""",
)

# ---------------------------------------------------------------------- 3, a real position

CARD3 = page(
    "PRICED ON CHAIN",
    """
<h1>A real position, <b>priced right now.</b></h1>
<div class="sub">Position #%(id)s on Robinhood Chain. Exact integer math, no floating point, and a
  fee rate measured over a full day of chain history.</div>
<div class="grow">
  <div class="nums">
    <div class="n"><div class="k">Market value</div><div class="v">%(value)s<em>USDG</em></div></div>
    <div class="n"><div class="k">Fees earned, per day</div><div class="v">%(feesPerDay)s<em>USDG</em></div></div>
    <div class="n lit"><div class="k">Sale price</div><div class="v">%(sale)s<em>USDG</em></div></div>
    <div class="n lit"><div class="k">Buyback</div><div class="v">%(buyback)s<em>USDG</em></div></div>
    <div class="n lit"><div class="k">Rent, 7 days</div><div class="v">%(rent)s<em>USDG</em></div></div>
  </div>
</div>
<div class="foot">Large because the pool is large: <b>%(apr)s%% fee APR</b>, a memecoin pair. The rent
  is half of what the position actually earned on chain. Not a rate anybody picked.</div>
"""
    % POSITION,
    """
  .nums { display:grid; grid-template-columns:repeat(5,1fr); gap:1px; background:var(--line);
          border:1px solid var(--line); border-radius:18px; overflow:hidden }
  .n { background:var(--panel); padding:30px 24px; display:flex; flex-direction:column; gap:14px }
  .n.lit { background:linear-gradient(180deg,rgba(245,184,75,.09),var(--panel) 70%) }
  .k { font-size:16px; font-weight:600; letter-spacing:.11em; color:var(--faint); line-height:1.3 }
  .v { font-size:44px; font-weight:700; letter-spacing:-.02em; font-variant-numeric:tabular-nums }
  .n.lit .v { color:var(--amber) }
  .v em { display:block; font-style:normal; font-size:16px; font-weight:600; letter-spacing:.14em;
          color:var(--faint); margin-top:8px }
""",
)

# ---------------------------------------------------------------------- 4, the layers

LAYERS = [
    ("Front ends, matching, curated vaults", "Where the product lives, and where a fee belongs", "top"),
    ("ScreeningList", "A published opinion on which pools are fit to deal in. The vault never reads it", ""),
    ("Builder codes", "Each side pays whoever brought them, out of its own money", ""),
    ("LeaseVault", "Immutable. No owner, no pause, no fee, no dependency", "base"),
]

CARD4 = page(
    "ARCHITECTURE",
    """
<h1>One primitive. <b>Everything else is replaceable.</b></h1>
<div class="sub">A gate welded into the bottom layer is either frozen forever or governed by
  somebody. So the bottom layer holds no opinions.</div>
<div class="grow">
  <div class="stack">
    """
    + "".join(
        '<div class="layer %s"><div class="nm">%s</div><div class="ds">%s</div></div>' % (cls, nm, ds)
        for nm, ds, cls in LAYERS
    )
    + """
  </div>
</div>
<div class="foot"><b>Only the bottom layer is permanent.</b> Anything above it can be rebuilt,
  competed with, or replaced without asking anyone.</div>
""",
    """
  .stack { display:flex; flex-direction:column; gap:12px }
  .layer { background:var(--panel); border:1px solid var(--line); border-radius:15px;
           padding:22px 30px; display:flex; align-items:baseline; gap:28px }
  .layer .nm { font-size:27px; font-weight:600; width:520px; flex:none; color:var(--muted) }
  .layer .ds { font-size:21px; color:var(--faint); line-height:1.3 }
  .layer.top { border-style:dashed; border-color:var(--line-hi) }
  .layer.base { border-color:rgba(245,184,75,.55);
                background:linear-gradient(180deg,rgba(245,184,75,.10),var(--panel) 70%);
                padding-top:28px; padding-bottom:28px }
  .layer.base .nm { color:var(--amber); font-size:31px; font-weight:700 }
  .layer.base .ds { color:var(--muted) }
""",
)

# ---------------------------------------------------------------------- 5, builder codes

CARD5 = page(
    "BUILDER CODES",
    """
<h1>The vault takes <b>nothing.</b></h1>
<div class="sub">Whoever brings a deal together still has to get paid, or every front end wraps the
  vault in a contract of its own and splits the liquidity.</div>
<div class="grow">
  <div class="flow">
    <div class="side">
      <div class="who">Seller</div>
      <div class="pipe">pays a flat amount, out of the proceeds<div class="ar">&darr;</div></div>
      <div class="dest">their builder</div>
    </div>
    <div class="middle">
      <div class="zero">0</div>
      <div class="zt">kept by the vault</div>
    </div>
    <div class="side">
      <div class="who">Financier</div>
      <div class="pipe">pays a flat amount, on top of the price<div class="ar">&darr;</div></div>
      <div class="dest">their builder</div>
    </div>
  </div>
</div>
<div class="foot"><b>Name nobody and nothing is charged.</b> Each side is capped at a hundredth of
  the price, because the party paying rarely builds the transaction they sign.</div>
""",
    """
  .flow { display:grid; grid-template-columns:1fr auto 1fr; gap:34px; align-items:center }
  .side { background:var(--panel); border:1px solid var(--line); border-radius:18px; padding:28px 30px;
          display:flex; flex-direction:column; gap:16px; text-align:center }
  .who { font-size:30px; font-weight:600 }
  .pipe { font-size:19px; color:var(--faint); line-height:1.35 }
  .ar { font-size:30px; color:var(--amber); margin-top:8px }
  .dest { font-size:25px; font-weight:600; color:var(--amber) }
  .middle { text-align:center; padding:0 12px }
  .zero { font-size:104px; font-weight:700; color:var(--dim); line-height:1 }
  .zt { font-size:16px; font-weight:600; letter-spacing:.14em; color:var(--faint); margin-top:12px }
""",
)

# ---------------------------------------------------------------------- 6, the one line

CARD6 = page(
    "ONE COMPARISON",
    """
<h1>Paid for the use of the asset. <b>Never for the passage of time.</b></h1>
<div class="grow">
  <div class="code mono">if (t.buybackPrice &gt; t.price) revert <b>BuybackAboveSale</b>();</div>
  <div class="why">A buyback above the sale price is a guaranteed spread collected on top of the
    rent: a financing cost in the clothes of a sale.</div>
</div>
<div class="foot">There is no owner here to forbid it later. <b>So it is one comparison, checkable
  by anyone who opens the file.</b></div>
""",
    """
  .code { background:var(--panel); border:1px solid rgba(245,184,75,.45); border-radius:18px;
          padding:46px 44px; font-size:41px; line-height:1.35; letter-spacing:-.01em;
          color:var(--muted); word-break:break-word }
  .code b { color:var(--amber); font-weight:700 }
  .why { font-size:26px; color:var(--muted); line-height:1.4; margin-top:34px; max-width:1200px }
""",
)

# ---------------------------------------------------------------------- 7, the freeze

CARD7 = page(
    "WHO CARRIES THE RISK",
    """
<h1>Freeze the asset and <b>the rent stops.</b></h1>
<div class="sub">The financier owns the position, so the financier carries an owner's risk. Rent
  accrues per usable second, and the unaccrued part goes back to the lessee.</div>
<div class="grow">
  <svg viewBox="0 0 1468 280" width="1468" height="280" xmlns="http://www.w3.org/2000/svg">
    <rect x="612" y="30" width="270" height="196" fill="rgba(255,139,123,.10)"
          stroke="rgba(255,139,123,.34)" stroke-width="1" rx="6"/>
    <path d="M40 210 L612 92" stroke="#F5B84B" stroke-width="5" fill="none" stroke-linecap="round"/>
    <path d="M612 92 L882 92" stroke="rgba(255,139,123,.75)" stroke-width="5" fill="none"
          stroke-dasharray="10 9" stroke-linecap="round"/>
    <path d="M882 92 L1428 22" stroke="#F5B84B" stroke-width="5" fill="none" stroke-linecap="round"/>
    <circle cx="612" cy="92" r="8" fill="#F5B84B"/>
    <circle cx="882" cy="92" r="8" fill="#F5B84B"/>
    <line x1="40" y1="252" x2="1428" y2="252" stroke="rgba(244,241,234,.16)" stroke-width="1"/>
    <text x="40" y="244" fill="rgba(244,241,234,.34)" font-family="Bahnschrift, sans-serif"
          font-size="20" font-weight="600">FUNDED</text>
    <text x="1428" y="244" fill="rgba(244,241,234,.34)" font-family="Bahnschrift, sans-serif"
          font-size="20" font-weight="600" text-anchor="end">TERM ENDS</text>
    <text x="747" y="262" fill="rgba(255,139,123,.85)" font-family="Bahnschrift, sans-serif"
          font-size="21" font-weight="600" text-anchor="middle">UNDERLYING FROZEN</text>
    <!-- Below the line, not across it: at x=300 the line sits near y=156. -->
    <text x="262" y="200" fill="rgba(244,241,234,.58)" font-family="Bahnschrift, sans-serif"
          font-size="23">rent accrues</text>
    <text x="747" y="66" fill="rgba(255,139,123,.85)" font-family="Bahnschrift, sans-serif"
          font-size="23" text-anchor="middle">rent stops</text>
    <text x="1180" y="90" fill="rgba(244,241,234,.58)" font-family="Bahnschrift, sans-serif"
          font-size="23" text-anchor="middle">and resumes</text>
  </svg>
</div>
<div class="foot">Two bounds keep it honest: a freeze counts <b>at most 6 hours</b> past the last
  observation, and <b>at most half a term</b> can ever be credited as frozen.</div>
""",
    """
  svg { display:block; margin:0 auto }
""",
)

# ---------------------------------------------------------------------- 8, roadmap

STEPS = [
    ("Contracts and the valuation API", "47 contract tests, 5 against live chain state. The API is running.", "done"),
    ("A curated vault", "Pooled financier capital, funding only what its curator approves.", "next"),
    ("Testnet", "Deployed, open to the waitlist.", ""),
    ("An independent audit, then mainnet", "In that order. Not the other one.", ""),
]

CARD8 = page(
    "ROADMAP",
    """
<h1>What exists, <b>and what comes next.</b></h1>
<div class="sub">Early, and we would rather say so.</div>
<div class="grow">
  <div class="steps">
    """
    + "".join(
        '<div class="step %s"><div class="dot"></div><div class="body">'
        '<div class="nm">%s</div><div class="ds">%s</div></div>'
        '<div class="state">%s</div></div>' % (cls, nm, ds, cls.upper())
        for nm, ds, cls in STEPS
    )
    + """
  </div>
</div>
<div class="foot"><b>Not audited. No contract deployed on any chain. No token.</b></div>
""",
    """
  .steps { display:flex; flex-direction:column; gap:12px }
  .step { background:var(--panel); border:1px solid var(--line); border-radius:15px;
          padding:22px 30px; display:flex; align-items:center; gap:24px }
  .dot { width:13px; height:13px; border-radius:50%; background:var(--dim); flex:none }
  .step.done .dot { background:var(--green) }
  .step.next .dot { background:var(--amber) }
  .step .body { flex:1 }
  .nm { font-size:27px; font-weight:600; margin-bottom:5px }
  .ds { font-size:20px; color:var(--faint); line-height:1.3 }
  .state { font-size:15px; font-weight:600; letter-spacing:.18em; color:var(--faint); flex:none }
  .step.done .state { color:var(--green) }
  .step.next .state { color:var(--amber) }
""",
)

CARDS = [
    ("card-1-acts.html", CARD1),
    ("card-2-not-a-loan.html", CARD2),
    ("card-3-position.html", CARD3),
    ("card-4-layers.html", CARD4),
    ("card-5-builders.html", CARD5),
    ("card-6-one-line.html", CARD6),
    ("card-7-freeze.html", CARD7),
    ("card-8-roadmap.html", CARD8),
]

if __name__ == "__main__":
    for name, html in CARDS:
        with io.open(os.path.join(HERE, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(html)
        print("  %s" % name)
    print("\n%d cards. Rasterise with ./render-cards.ps1" % len(CARDS))
