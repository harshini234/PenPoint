from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
st.set_page_config(page_title="PenPoint", page_icon="🐄", layout="wide",
                   initial_sidebar_state="expanded")

from penpoint import theme as T
from penpoint import data as D

SECTIONS = [
    ("lots", "Lot management", ":material/inventory_2:", [("cards", "Lots and cattle"), ("add", "Add or import data"), ("operation", "Constraints and assumptions")]),
    ("herd", "Herd status", ":material/monitor_heart:", [("lots", "Risk overview")]),
    ("options", "Management options", ":material/alt_route:", [
        ("compare", "Treatment options"), ("costs", "Lot-level cost analysis"), ("scenario", "Scenario analysis"), ("plan", "Decision summary"),
        ("today", "Daily action list"), ("tracking", "Treatment response")]),
    ("about", "About the model", ":material/fact_check:", [("equations", "Methods and equations"), ("works", "Model validation"),
                                                          ("sources", "Parameter sources"), ("reqs", "Brief requirements")]),
]

ss = st.session_state
ss.setdefault("stage", "landing")
ss.setdefault("section", "herd")
ss.setdefault("sub", "lots")


def go(stage=None, section=None, sub=None):
    if stage:
        ss.stage = stage
    if section:
        ss.section = section
        ss.sub = sub or next(s for s in SECTIONS if s[0] == section)[3][0][0]
        ss.open_lot = None
        ss.herd_lot = None
    elif sub:
        ss.sub = sub
        ss.open_lot = None
        ss.herd_lot = None


def landing():
    T.inject_landing()
    st.html(f"""<div class="lp-nav"><div class="b">{T.logo(30)}PenPoint</div>
<div class="r">AISFS × Merck Animal Health Hackathon 2026</div></div>
<div class="lp-hero"><h1>PenPoint</h1>
<p>Cattle analytics and BRD decision management for the first 45 days on feed.</p></div>""")
    _, mid, _ = st.columns([1, 0.6, 1])
    with mid:
        st.button("Open PenPoint", key="enter", on_click=go, kwargs=dict(stage="signin"), width="stretch")


def signin():
    T.inject_landing(blur=True)
    with st.container(key="signin_card"):
        st.html(f"""<div class="si-b">{T.logo(28)}PenPoint</div>
<p class="si-h">Sign in</p><p class="si-p">Pick up where your crew left off.</p>""")
        st.text_input("Email", placeholder="you@yourfeedyard.com")
        st.text_input("Password", type="password")
        st.button("Sign in", key="signin_go", type="primary", on_click=go, kwargs=dict(stage="app"), width="stretch")
        st.button("Back", key="signin_back", type="tertiary", on_click=go, kwargs=dict(stage="landing"), width="stretch")


def sidebar():
    with st.sidebar:
        st.html(f'<div class="sb-brand">{T.logo(30)}<span>PenPoint</span></div>'
                f'<p class="sb-label" style="margin-top:0;color:#BFD3C7">{T.esc(ss.yard["name"])}</p>')
        st.html('<p class="sb-label">Workspace</p>')
        for sid, label, icon, subs in SECTIONS:
            if sid == "about":
                st.html('<p class="sb-label">Reference</p>')
            active = ss.section == sid
            st.button(label, key=f"nav_{sid}", icon=icon, type="primary" if active else "tertiary",
                      on_click=go, kwargs=dict(section=sid), width="stretch")
            if active:
                for sub, sl in subs:
                    st.button(sl, key=f"sub_{sid}_{sub}", type="primary" if ss.sub == sub else "tertiary",
                              on_click=go, kwargs=dict(sub=sub), width="stretch")
        sh = D.sensehub_status()
        if sh and sh["stale"]:
            st.html(f'<p class="sb-foot" style="color:#E9C46A">SenseHub {sh["label"]}</p>')
        st.button("Sign out", key="signout", icon=":material/logout:", type="tertiary", on_click=go, kwargs=dict(stage="landing"))


def app():
    T.inject_base()
    D.sync()
    sidebar()
    from penpoint.views import about, herd, lots, options
    valid = {sid: [x[0] for x in subs] for sid, _, _, subs in SECTIONS}
    if ss.section not in valid:
        ss.section, ss.sub = "herd", "lots"
    if ss.sub not in valid[ss.section]:
        ss.sub = valid[ss.section][0]
    needs_lots = ss.section in ("herd", "options")
    if needs_lots and ss.lots.empty:
        return empty_state()
    {"lots": lots.render, "herd": herd.render, "options": options.render, "about": about.render}[ss.section](ss.sub, None)


def empty_state():
    T.header("No cattle yet", "Import your yard's data to see risk, treatment options and the plan.")
    with st.container(key="feature_empty"):
        st.html('<p class="pp-h" style="color:#fff">Start by importing data</p><p style="color:#DCE8E0;max-width:70ch">Upload a cattle file (one row per animal, '
                'with its lot), and optionally health records and a SenseHub report, under Lot management, Add or import data. '
                'You can also create a lot by hand.</p>')
        st.button("Add or import data", key="empty_add", on_click=go, kwargs=dict(section="lots", sub="add"))


if ss.stage == "landing":
    T.inject_base()
    landing()
elif ss.stage == "signin":
    T.inject_base()
    signin()
else:
    app()
