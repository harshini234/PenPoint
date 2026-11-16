from __future__ import annotations

import base64
import math

W, H = 1600, 900


def _crest(x0, x1, base, waves, step=8):
    pts = []
    x = x0
    while x <= x1:
        y = base + sum(a * math.sin((x + ph) / per) for a, per, ph in waves)
        pts.append((x, y))
        x += step
    return pts


def _hill_path(pts, bottom=H + 20):
    d = f"M{pts[0][0]:.1f},{bottom} L{pts[0][0]:.1f},{pts[0][1]:.1f} "
    d += " ".join(f"L{x:.1f},{y:.1f}" for x, y in pts[1:])
    d += f" L{pts[-1][0]:.1f},{bottom} Z"
    return d


def _y_at(pts, x):
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        if xa <= x <= xb:
            return ya + (yb - ya) * (x - xa) / (xb - xa)
    return pts[-1][1]


COW = """
<g class="cow" fill="#18211D">
  <path d="M30,28 C32,16 52,13 72,15 C92,13 108,16 112,26 C116,36 113,52 104,56 C88,60 52,60 40,56 C33,53 29,40 30,28 Z"/>
  <path d="M38,24 C30,26 22,34 18,44 C14,52 10,58 9,63 C8,68 13,71 19,70 C25,69 28,64 30,58 C33,50 38,44 44,40 Z"/>
  <path d="M23,41 C17,38 12,40 9,44 C13,46 19,46 24,45 Z"/>
  <path d="M38,52 L46,52 L45.2,80 L39.4,80 Z"/>
  <path d="M48,53 L55,53 L54.2,79 L49,79 Z"/>
  <path d="M91,51 C95,54 99,54 101,51 L100,80 L94,80 Z"/>
  <path d="M102,50 L109,49 L108,79 L103,79 Z"/>
  <path d="M111,26 C116,34 116.5,46 114.5,57" fill="none" stroke="#18211D" stroke-width="2.6" stroke-linecap="round"/>
  <ellipse cx="114.6" cy="60" rx="3" ry="5"/>
  <path d="M52,17 C66,13 86,13 100,17" fill="none" stroke="#3A4A42" stroke-width="1.6" stroke-linecap="round" opacity=".55"/>
</g>
"""


def hero_svg(with_cow: bool = True) -> str:
    far = _crest(-20, W + 20, 585, [(18, 210, 0), (10, 90, 40)])
    midfar = _crest(-20, W + 20, 640, [(26, 260, 300), (9, 110, 10)])
    cowhill = _crest(-20, W + 20, 700, [(70, 330, -880), (8, 120, 0)])
    near = _crest(-20, W + 20, 770, [(46, 300, 120), (7, 95, 30)])
    front = _crest(-20, W + 20, 842, [(18, 240, 500), (5, 70, 0)])

    cx = 1110
    cy = _y_at(near, cx + 80)
    cow = (f'<ellipse cx="{cx + 78}" cy="{cy + 3}" rx="74" ry="7" fill="#0E2A1F" opacity=".25"/>'
           f'<g transform="translate({cx},{cy - 106}) scale(1.36)">{COW}</g>') if with_cow else ""

    posts, rails_top, rails_low = [], [], []
    for x in range(40, 760, 58):
        y = _y_at(near, x)
        posts.append(f'<rect x="{x - 2.5}" y="{y - 46}" width="5" height="50" rx="1.6" fill="#173D2E"/>')
        rails_top.append((x, y - 38))
        rails_low.append((x, y - 20))
    rail = lambda pts: "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    tufts = []
    for i, x in enumerate(range(860, 1600, 61)):
        y = _y_at(front, x) + 6 + (i % 3) * 5
        tufts.append(f'<path d="M{x},{y} q-3,-11 -7,-15 M{x},{y} q1,-13 3,-18 M{x},{y} q4,-9 9,-12" '
                     f'stroke="#2E6B4E" stroke-width="2" fill="none" stroke-linecap="round" opacity=".7"/>')

    trees = []
    for tx, s in ((210, 1.0), (262, .8), (1390, 1.1), (1440, .75), (930, .7)):
        ty = _y_at(far, tx)
        trees.append(f'<g opacity=".55" fill="#6E967D"><circle cx="{tx}" cy="{ty - 14 * s}" r="{15 * s}"/>'
                     f'<circle cx="{tx + 13 * s}" cy="{ty - 8 * s}" r="{11 * s}"/><circle cx="{tx - 12 * s}" cy="{ty - 7 * s}" r="{10 * s}"/></g>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMax slice">
<defs>
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#C3CBC8"/><stop offset=".45" stop-color="#DCE1DF"/><stop offset="1" stop-color="#F1F3F2"/>
  </linearGradient>
  <radialGradient id="glow" cx=".72" cy=".18" r=".55">
    <stop offset="0" stop-color="#FFFFFF" stop-opacity=".85"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#C9D8CE"/><stop offset="1" stop-color="#B2C7B9"/></linearGradient>
  <linearGradient id="g2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#9DBFA8"/><stop offset="1" stop-color="#7FA88D"/></linearGradient>
  <linearGradient id="g3" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6FA683"/><stop offset="1" stop-color="#478260"/></linearGradient>
  <linearGradient id="g4" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3D7A5A"/><stop offset="1" stop-color="#2A6247"/></linearGradient>
  <linearGradient id="g5" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#22573F"/><stop offset="1" stop-color="#143A2B"/></linearGradient>
  <linearGradient id="sheen" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#FFFFFF" stop-opacity="0"/><stop offset=".5" stop-color="#FFFFFF" stop-opacity=".55"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>
  </linearGradient>
  <filter id="soft" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="14"/></filter>
  <filter id="grain"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" stitchTiles="stitch"/>
    <feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 .55 0"/></filter>
</defs>
<rect width="{W}" height="{H}" fill="url(#sky)"/>
<rect width="{W}" height="{H}" fill="url(#glow)"/>
<path d="M-100,260 C300,120 700,420 1100,250 S1600,140 1800,230" stroke="url(#sheen)" stroke-width="70" fill="none" filter="url(#soft)" opacity=".8"/>
<path d="M-100,420 C380,300 760,520 1180,380 S1640,300 1800,360" stroke="url(#sheen)" stroke-width="38" fill="none" filter="url(#soft)" opacity=".6"/>
{''.join(trees)}
<path d="{_hill_path(far)}" fill="url(#g1)"/>
<path d="{_hill_path(midfar)}" fill="url(#g2)"/>
<path d="{_hill_path(cowhill)}" fill="url(#g3)"/>
<path d="{_hill_path(near)}" fill="url(#g4)"/>
{cow}
<g opacity=".9">{''.join(posts)}
<path d="{rail(rails_top)}" stroke="#173D2E" stroke-width="3.2" fill="none" stroke-linecap="round"/>
<path d="{rail(rails_low)}" stroke="#173D2E" stroke-width="3.2" fill="none" stroke-linecap="round"/></g>
<path d="{_hill_path(front)}" fill="url(#g5)"/>
{''.join(tufts)}
<rect width="{W}" height="{H}" filter="url(#grain)" opacity=".06"/>
</svg>"""


def data_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


LOGO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" width="{s}" height="{s}" aria-hidden="true">
<path d="M20 2.5c-7.6 0-13.7 6-13.7 13.5 0 9.6 11.1 19.6 12.4 20.8a2 2 0 0 0 2.6 0C22.6 35.6 33.7 25.6 33.7 16 33.7 8.5 27.6 2.5 20 2.5z" fill="{bg}"/>
<g stroke="{fg}" stroke-width="2.3" stroke-linecap="round"><path d="M12.8 12.6h14.4M12.8 18.4h14.4"/><path d="M14.6 10v11.4M25.4 10v11.4"/></g>
</svg>"""


def logo(size=30, bg="#DCEB8A", fg="#0F3427") -> str:
    return LOGO.format(s=size, bg=bg, fg=fg)
