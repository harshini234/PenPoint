from __future__ import annotations

import html as _html

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from . import art

FOREST = "#0F3427"
PINE = "#1D5640"
SAGE = "#6FAF8C"
HAY = "#DCEB8A"
FOG = "#EDF1EE"
INK = "#13261F"
MUTED = "#5F7068"
LINE = "#DCE4DF"

SERIES = ["#1F7A52", "#3577D6", "#E5682F", "#9D55C4", "#B88A00"]
OPTION_COLOR = {"A": "#8A9791", "K": "#8A9791", "B": "#3577D6", "M": "#3577D6", "C": "#1F7A52",
                "C+": "#B88A00", "X": "#B88A00", "D": "#9D55C4"}
STATUS = {"high": "#C8553D", "watch": "#D98F1F", "low": "#2F8A5E", "unknown": "#8A9791"}

FONT = "Instrument Sans, system-ui, sans-serif"
DISPLAY = "Bricolage Grotesque, Instrument Sans, sans-serif"


def _template():
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family=FONT, color=INK, size=13),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        colorway=SERIES,
        margin=dict(l=8, r=8, t=36, b=8),
        title=dict(font=dict(family=DISPLAY, size=16, color=INK), x=0, xanchor="left", y=0.98),
        xaxis=dict(automargin=True, gridcolor="#E7EDE9", zeroline=False, linecolor=LINE, tickfont=dict(color=MUTED), title=dict(font=dict(color=MUTED, size=12))),
        yaxis=dict(automargin=True, gridcolor="#E7EDE9", zeroline=False, linecolor=LINE, tickfont=dict(color=MUTED), title=dict(font=dict(color=MUTED, size=12))),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(color=MUTED, size=12), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="white", bordercolor=LINE, font=dict(family=FONT, color=INK, size=12)),
        barcornerradius=4,
        bargap=0.35,
    )
    return t


pio.templates["penpoint"] = _template()
pio.templates.default = "penpoint"

PLOT_CONFIG = {"displayModeBar": False, "responsive": True}


def chart(fig, height=None, key=None):
    if height:
        fig.update_layout(height=height)
    st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG, key=key, theme=None)


BASE_CSS = f"""
<style>
:root {{ --forest:{FOREST}; --pine:{PINE}; --sage:{SAGE}; --hay:{HAY}; --fog:{FOG}; --ink:{INK}; --muted:{MUTED}; --line:{LINE}; }}
[data-testid="stDecoration"], footer, #MainMenu, [data-testid="stStatusWidget"],
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"] {{ display:none !important; }}
header[data-testid="stHeader"] {{ background:transparent !important; height:3rem; }}
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapsedControl"] button {{ background:{FOREST} !important; color:{HAY} !important;
  border-radius:12px !important; }}
[data-testid="stExpandSidebarButton"] {{ width:40px !important; height:40px !important; margin:6px 0 0 10px; }}
[data-testid="stExpandSidebarButton"] span, [data-testid="stExpandSidebarButton"] svg {{ color:{HAY} !important; fill:{HAY} !important; }}
.block-container {{ padding: 3.6rem 2.6rem 4rem 2.6rem !important; max-width: 1480px; }}
h1, h2, h3, h4 {{ letter-spacing: -0.01em; }}
p, li {{ max-width: 78ch; }}
:focus-visible {{ outline: 2px solid var(--pine) !important; outline-offset: 2px; }}

[class*="st-key-card"] {{ background:#fff; border:1px solid var(--line); border-radius:22px; padding:20px 22px 18px 22px;
  box-shadow: 0 1px 0 rgba(15,52,39,.03); }}
[class*="st-key-tile"] {{ background:#fff; border:1px solid var(--line); border-radius:18px; padding:14px 16px; }}
[class*="st-key-feature"] {{ background: radial-gradient(120% 140% at 100% 0%, #2A6A50 0%, var(--forest) 62%); color:#EAF2EC;
  border-radius:24px; padding:22px 24px; }}
[class*="st-key-feature"] p, [class*="st-key-feature"] li, [class*="st-key-feature"] span, [class*="st-key-feature"] label {{ color:#DCE8E0; }}
[class*="st-key-feature"] h3 {{ color:#fff; }}
[class*="st-key-feature"] [data-testid="stAlertContainer"] p, [class*="st-key-feature"] [data-testid="stAlert"] p {{ color:{INK} !important; }}
[class*="st-key-soft"] {{ background:#F6F9F7; border:1px dashed #C9D6CE; border-radius:18px; padding:16px 18px; }}

.pp-head {{ display:flex; align-items:flex-end; justify-content:space-between; gap:24px; margin: 0 0 1.1rem 0; }}
.pp-title {{ font-family:{DISPLAY}; font-weight:650; font-size:2.05rem; line-height:1.1; color:var(--ink); margin:0; letter-spacing:-0.02em; }}
.pp-sub {{ color:var(--muted); font-size:1rem; margin:.35rem 0 0 0; max-width:70ch; }}
.pp-asof {{ color:var(--muted); font-size:.85rem; white-space:nowrap; padding:7px 12px; border:1px solid var(--line); border-radius:999px; background:#fff; }}
.pp-h {{ font-family:{DISPLAY}; font-weight:620; font-size:1.18rem; color:var(--ink); margin:0 0 .15rem 0; letter-spacing:-0.01em; }}
.pp-note {{ color:var(--muted); font-size:.86rem; margin:.15rem 0 .6rem 0; }}

.pp-kpi {{ display:flex; gap:14px; align-items:center; }}
.pp-kpi .ic {{ width:46px; height:46px; border-radius:50%; display:grid; place-items:center; flex:none; }}
.pp-kpi .lab {{ color:var(--muted); font-size:.84rem; margin:0; }}
.pp-kpi .val {{ font-family:{DISPLAY}; font-weight:650; font-size:1.75rem; line-height:1.1; color:var(--ink); margin:2px 0 0 0; font-variant-numeric: tabular-nums; }}
.pp-kpi .dlw {{ margin:.3rem 0 0 0; }}
.pp-kpi .dl {{ font-size:.76rem; padding:2px 8px; border-radius:999px; vertical-align:middle; font-family:{FONT}; font-weight:600; }}
.dl.good {{ background:#E3F1E7; color:#1E6B45; }} .dl.bad {{ background:#F8E4DE; color:#9A3B27; }} .dl.flat {{ background:#EEF1EF; color:#5F7068; }}

.chip {{ display:inline-flex; align-items:center; gap:6px; font-size:.78rem; font-weight:600; padding:3px 10px; border-radius:999px; line-height:1.4; white-space:nowrap; }}
.chip .dot {{ width:7px; height:7px; border-radius:50%; }}
.chip.high {{ background:#F8E3DD; color:#93351F; }} .chip.high .dot {{ background:{STATUS['high']}; }}
.chip.watch {{ background:#FBEFD9; color:#87570A; }} .chip.watch .dot {{ background:{STATUS['watch']}; }}
.chip.low {{ background:#E2F1E7; color:#1C6542; }} .chip.low .dot {{ background:{STATUS['low']}; }}
.chip.unknown {{ background:#EEF1EF; color:#55635C; }} .chip.unknown .dot {{ background:{STATUS['unknown']}; }}
.chip.info {{ background:#E7EEF9; color:#24538F; }} .chip.info .dot {{ background:#3577D6; }}
.chip.hay {{ background:{HAY}; color:{FOREST}; }}
.chip.ghost {{ background:#fff; color:var(--muted); border:1px solid var(--line); }}

.lotcard .top {{ display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }}
.lotcard .id {{ font-family:{DISPLAY}; font-weight:650; font-size:1.2rem; color:var(--ink); margin:0; }}
.lotcard .meta {{ color:var(--muted); font-size:.83rem; margin:.1rem 0 .7rem 0; }}
.lotcard .row {{ display:flex; gap:18px; flex-wrap:wrap; }}
.lotcard .row div {{ min-width:64px; }}
.lotcard .k {{ color:var(--muted); font-size:.74rem; margin:0; }}
.lotcard .v {{ font-weight:650; font-size:1rem; color:var(--ink); margin:0; font-variant-numeric: tabular-nums; }}
.meter {{ height:6px; background:#EDF2EF; border-radius:999px; overflow:hidden; margin:.75rem 0 .2rem 0; position:relative; }}
.meter span {{ position:absolute; top:0; bottom:0; border-radius:999px; }}

.cowgrid {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap:10px; }}
.cow {{ background:#fff; border:1px solid var(--line); border-radius:16px; padding:11px 12px; }}
.cow .tag {{ display:inline-block; font-family:{DISPLAY}; font-weight:700; font-size:1.02rem; background:{HAY}; color:{FOREST};
  padding:1px 9px 2px 9px; border-radius:7px 7px 12px 12px; }}
.cow .eid {{ color:var(--muted); font-size:.7rem; margin:.35rem 0 .35rem 0; font-variant-numeric: tabular-nums; }}
.cow .ln {{ font-size:.8rem; color:var(--ink); margin:0; }}
.cow.dead {{ opacity:.55; }}

.action {{ display:flex; gap:14px; align-items:flex-start; padding:12px 0; border-bottom:1px solid #EEF2EF; }}
.action:last-child {{ border-bottom:none; }}
.action .when {{ flex:none; width:78px; font-size:.78rem; color:var(--muted); padding-top:2px; }}
.action .what {{ font-weight:600; color:var(--ink); margin:0; }}
.action .why {{ color:var(--muted); font-size:.86rem; margin:.15rem 0 0 0; }}

.legend-row {{ display:flex; gap:16px; flex-wrap:wrap; font-size:.8rem; color:var(--muted); margin:.2rem 0 .4rem 0; }}
.legend-row i {{ display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:6px; vertical-align:-1px; }}

.penmap {{ display:grid; gap:6px; }}
.pen {{ border-radius:10px; padding:8px 8px 7px 8px; min-height:58px; color:#fff; font-size:.72rem; position:relative; }}
.pen b {{ display:block; font-size:.86rem; font-family:{DISPLAY}; }}
.pen.empty {{ background:#E6ECE8; color:#7A8A82; }}
.alley {{ height:10px; border-radius:4px; background: repeating-linear-gradient(90deg,#D3DDD7 0 14px, transparent 14px 22px); margin:4px 0; }}

div[data-testid="stTabs"] button[role="tab"] {{ font-weight:600; }}
div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{ background:{PINE}; }}

.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{ background:{PINE}; border-color:{PINE}; color:#fff; }}
.stButton > button[kind="primary"]:hover {{ background:#174734; border-color:#174734; }}
[class*="st-key-feature"] .stButton > button {{ background:{HAY}; color:{FOREST}; border:none; font-weight:650; }}
[class*="st-key-feature"] .stButton > button:hover {{ background:#CFE07A; color:{FOREST}; }}
[class*="st-key-feature"] .stButton p, [class*="st-key-feature"] .stDownloadButton p {{ color:{FOREST} !important; font-weight:650; }}
[class*="st-key-feature"] .stDownloadButton > button {{ background:{HAY}; color:{FOREST}; border:none; }}
[class*="st-key-open_"] button {{ padding:4px 14px; min-height:0; font-size:.85rem; }}

section[data-testid="stSidebar"] {{ width: 272px !important; }}
section[data-testid="stSidebar"] > div {{ padding-top: .4rem; }}
section[data-testid="stSidebar"] .stButton > button {{ width:100%; justify-content:flex-start; border:none; background:transparent;
  color:#B9CCC1; font-weight:500; padding:9px 14px; border-radius:12px; min-height:0; }}
section[data-testid="stSidebar"] .stButton > button:hover {{ background:rgba(255,255,255,.06); color:#fff; }}
section[data-testid="stSidebar"] .stButton > button div {{ justify-content:flex-start; text-align:left; }}
section[data-testid="stSidebar"] .stButton > button p {{ text-align:left; }}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {{ background:rgba(220,235,138,.12); color:{HAY}; font-weight:650; }}
section[data-testid="stSidebar"] [class*="st-key-sub_"] button {{ padding:6px 14px 6px 46px; font-size:.9rem; color:#9DB4A7; }}
section[data-testid="stSidebar"] [class*="st-key-sub_"] button[kind="primary"] {{ background:transparent; color:#fff; }}
section[data-testid="stSidebar"] [class*="st-key-sub_"] button[kind="primary"]::before {{ content:""; position:absolute; left:30px; top:50%;
  width:6px; height:6px; margin-top:-3px; border-radius:50%; background:{HAY}; }}
section[data-testid="stSidebar"] .st-key-signout button {{ color:#9DB4A7; font-size:.88rem; }}
.sb-brand {{ display:flex; align-items:center; gap:10px; padding:4px 6px 14px 6px; }}
.sb-brand span {{ font-family:{DISPLAY}; font-weight:700; font-size:1.45rem; color:#fff; letter-spacing:-0.02em; }}
.sb-label {{ color:#7F9A8B; font-size:.78rem; margin:14px 8px 4px 8px; }}
.sb-foot {{ color:#7F9A8B; font-size:.76rem; margin:16px 8px 0 8px; line-height:1.45; }}
section[data-testid="stSidebar"] [data-baseweb="select"] > div {{ background:#174634; border-color:#24543F; border-radius:14px; }}

.eqrow {{ display:flex; gap:12px; padding:8px 0; border-bottom:1px solid #EEF2EF; }}
.eqrow:last-child {{ border-bottom:none; }}
.eqn {{ flex:none; width:40px; color:var(--muted); font-size:.82rem; padding-top:2px; font-variant-numeric: tabular-nums; }}
.eqf {{ margin:0; font-weight:600; color:var(--ink); font-size:.92rem; }}
.eqv {{ margin:.15rem 0 0 0; color:#33473D; font-size:.9rem; font-variant-numeric: tabular-nums; }}
.eqw {{ margin:.15rem 0 0 0; color:var(--muted); font-size:.82rem; }}
.lotrow {{ display:flex; align-items:center; gap:14px; }}
.lotrow .nm {{ font-family:{DISPLAY}; font-weight:650; font-size:1.08rem; color:var(--ink); margin:0; }}
.lotrow .sub {{ color:var(--muted); font-size:.85rem; margin:0; }}
@media (prefers-reduced-motion: reduce) {{ * {{ animation:none !important; transition:none !important; }} }}
</style>
"""


def inject_base():
    st.html(BASE_CSS)


def inject_landing(blur=False):
    uri = art.data_uri(art.hero_svg())
    overlay = "linear-gradient(rgba(233,238,235,.55), rgba(233,238,235,.55))," if blur else ""
    st.html(f"""<style>
section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] {{ display:none !important; }}
.stApp {{ background: {overlay} url("{uri}") center bottom / cover no-repeat fixed, #DCE1DF; }}
.block-container {{ max-width: 1180px; padding-top: 1.4rem !important; }}
.lp-nav {{ display:flex; justify-content:space-between; align-items:center; padding:10px 18px; border-radius:999px;
  background: rgba(255,255,255,.42); border:1px solid rgba(255,255,255,.7); backdrop-filter: blur(14px); }}
.lp-nav .b {{ display:flex; align-items:center; gap:10px; font-family:{DISPLAY}; font-weight:700; font-size:1.25rem; color:{FOREST}; }}
.lp-nav .r {{ color:#3F5248; font-size:.9rem; }}
.lp-hero {{ text-align:center; margin: 12vh auto 0 auto; max-width: 820px; }}
.lp-hero h1 {{ font-family:{DISPLAY}; font-weight:700; font-size: clamp(3.4rem, 8.5vw, 7.4rem); line-height:.92; letter-spacing:-0.045em;
  color:{FOREST}; margin:0; padding:0; font-variation-settings: "opsz" 96; }}
.lp-hero p {{ font-size: clamp(1.05rem, 1.6vw, 1.3rem); color:#33473D; margin: 1.1rem auto 0 auto; max-width: 52ch; }}
.lp-hero .tick {{ display:inline-block; margin-top:1.1rem; font-size:.86rem; color:#3F5248; padding:6px 14px; border-radius:999px;
  background: rgba(255,255,255,.5); border:1px solid rgba(255,255,255,.75); }}

.st-key-enter button {{ margin-top: 1.6rem; padding: 14px 34px; font-size:1.05rem; font-weight:650; border-radius:999px;
  background: rgba(255,255,255,.62); color:{FOREST}; border:1px solid rgba(255,255,255,.95);
  box-shadow: 0 0 0 6px rgba(220,235,138,.35), 0 0 38px 6px rgba(220,235,138,.55); backdrop-filter: blur(10px);
  animation: pp-breathe 3.2s ease-in-out infinite; }}
.st-key-enter button:hover {{ background:{HAY}; color:{FOREST}; border-color:{HAY}; }}
@keyframes pp-breathe {{ 0%,100% {{ box-shadow: 0 0 0 6px rgba(220,235,138,.30), 0 0 30px 4px rgba(220,235,138,.45); }}
  50% {{ box-shadow: 0 0 0 9px rgba(220,235,138,.42), 0 0 46px 10px rgba(220,235,138,.62); }} }}
.st-key-signin_card {{ max-width: 430px; margin: 10vh auto 0 auto; background: rgba(255,255,255,.72); border:1px solid rgba(255,255,255,.9);
  backdrop-filter: blur(18px); border-radius: 28px; padding: 30px 32px 24px 32px; box-shadow: 0 30px 80px -30px rgba(15,52,39,.35); }}
.si-b {{ display:flex; align-items:center; gap:10px; font-family:{DISPLAY}; font-weight:700; font-size:1.3rem; color:{FOREST}; }}
.si-h {{ font-family:{DISPLAY}; font-weight:650; font-size:1.7rem; color:{INK}; margin:1.1rem 0 .2rem 0; letter-spacing:-0.02em; }}
.si-p {{ color:{MUTED}; font-size:.92rem; margin:0 0 .9rem 0; }}
.si-lock {{ display:flex; gap:10px; align-items:flex-start; background:#F1F5F2; border-radius:14px; padding:10px 12px; color:#41544A; font-size:.84rem; margin:.4rem 0 .9rem 0; }}
.st-key-signin_go button, .st-key-signin_back button {{ width:100%; }}
</style>""")


def esc(x) -> str:
    return _html.escape(str(x))


def header(title: str, sub: str = "", asof: str | None = None):
    right = f'<div class="pp-asof">Data as of {esc(asof)}</div>' if asof else ""
    st.html(f'<div class="pp-head"><div><h1 class="pp-title">{esc(title)}</h1>'
            f'{f"<p class=pp-sub>{esc(sub)}</p>" if sub else ""}</div>{right}</div>')


def h(title: str, note: str = ""):
    st.html(f'<p class="pp-h">{esc(title)}</p>{f"<p class=pp-note>{esc(note)}</p>" if note else ""}')


ICONS = {
    "cow": '<path d="M5 9c0-2 2-3 4-3h6c2 0 4 1 4 3v4c0 2-2 3-4 3H9c-2 0-4-1-4-3z"/><path d="M5 9 3 7M19 9l2-2M9 16v3M15 16v3"/>',
    "alert": '<path d="M12 4 2.5 20h19z"/><path d="M12 10v4M12 17v.5"/>',
    "pulse": '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
    "dollar": '<path d="M12 3v18M16.5 7.5c-.8-1.3-2.4-2-4.5-2-2.5 0-4 1.2-4 3s1.6 2.6 4 3.1 4.5 1.3 4.5 3.3-1.8 3.1-4.5 3.1c-2.3 0-4-.8-4.8-2.3"/>',
    "pill": '<rect x="3" y="8.5" width="18" height="7" rx="3.5" transform="rotate(-35 12 12)"/><path d="m9.2 8.3 5.6 7.4"/>',
    "heart": '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "signal": '<path d="M4 18h2M9 18v-4M14 18v-8M19 18V5"/>',
    "cloud": '<path d="M7 18h10a4 4 0 0 0 .5-8A6 6 0 0 0 6 9.5 4.3 4.3 0 0 0 7 18z"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "lock": '<rect x="5" y="10.5" width="14" height="9.5" rx="2.4"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5"/>',
    "doc": '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4M9.5 12h6M9.5 16h6"/>',
    "pen": '<rect x="3.5" y="5" width="17" height="14" rx="2"/><path d="M3.5 12h17M10 5v14"/>',
}


def _img(svg: str, size, alt=""):
    import base64
    return f'<img src="data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}" width="{size}" height="{size}" alt="{alt}" style="display:block">'


def icon(name, color=PINE, size=22, sw=1.8):
    return _img(f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
                f'stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>', size)


def logo(size=30):
    return _img(art.logo(size), size, "")


BADGE = {"pine": ("#DDEDE3", PINE), "hay": ("#EEF5C8", "#5D6B12"), "rust": ("#F6E1DA", "#A2402A"),
         "sky": ("#E2EBF8", "#2A5E9F"), "violet": ("#EEE4F5", "#6E3B8F"), "amber": ("#FBEFD9", "#8A5A08")}


def kpi(label, value, icon_name="pulse", tone="pine", delta=None, delta_good=None, key=None):
    bg, fg = BADGE[tone]
    dl = ""
    if delta:
        cls = "flat" if delta_good is None else ("good" if delta_good else "bad")
        dl = f'<span class="dl {cls}">{esc(delta)}</span>'
    body = (f'<div class="pp-kpi"><div class="ic" style="background:{bg}">{icon(icon_name, fg)}</div>'
            f'<div><p class="lab">{esc(label)}</p><p class="val">{esc(value)}</p>{f"<p class=dlw>{dl}</p>" if dl else ""}</div></div>')
    with st.container(key=key or f"tile_{abs(hash((label, value))) % 10**8}"):
        st.html(body)


def chip(text, kind="ghost", dot=True):
    d = '<span class="dot"></span>' if dot and kind in ("high", "watch", "low", "unknown", "info") else ""
    return f'<span class="chip {kind}">{d}{esc(text)}</span>'


def risk_band(p_high: float, lo: float, hi: float, cut: float):
    if lo < cut < hi and 0.2 < p_high < 0.8:
        return "watch", "Uncertain"
    if p_high >= 0.5:
        return "high", "High risk"
    if p_high >= 0.2:
        return "watch", "Watch"
    return "low", "Low risk"


def legend(items):
    st.html('<div class="legend-row">' + "".join(f'<span><i style="background:{c}"></i>{esc(t)}</span>' for t, c in items) + "</div>")


def work(steps, label="Show the work", expanded=False):
    return
    with st.expander(label, icon=":material/calculate:", expanded=expanded):
        html = []
        for stp in steps:
            n, f, v = stp[0], stp[1], stp[2] if len(stp) > 2 else ""
            w = stp[3] if len(stp) > 3 else ""
            html.append(f'<div class="eqrow"><span class="eqn">{f"({n})" if n else ""}</span><div><p class="eqf">{esc(f)}</p>'
                        f'{f"<p class=eqv>{esc(v)}</p>" if v else ""}{f"<p class=eqw>{esc(w)}</p>" if w else ""}</div></div>')
        st.html("".join(html))


def money(v, signed=False):
    if signed:
        return f"{'+' if v >= 0 else '−'}${abs(v):,.0f}"
    return f"{'−' if v < 0 else ''}${abs(v):,.0f}"
