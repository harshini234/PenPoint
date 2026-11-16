from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .. import data as D
from .. import db
from .. import theme as T
from ..theme import esc

ss = st.session_state


def _sync():
    D.save_weather(D.fetch_weather(ss.yard["lat"], ss.yard["lon"]), f"Open-Meteo forecast, synced {pd.Timestamp.now():%b %d %H:%M}")


def auto():
    if ss.get("_wx_tried"):
        return
    ss._wx_tried = True
    last = db.get_meta("weather_synced")
    if last and (pd.Timestamp.now() - pd.Timestamp(last)).total_seconds() < 6 * 3600:
        return
    try:
        _sync()
        D.sync()
    except Exception:
        pass


def card():
    auto()
    y = ss.yard
    w, src = ss.weather
    with st.container(key="feature_yard"):
        st.html(f'<p class="pp-note" style="color:#BFD3C7;margin:0">{esc(y["region"])}</p><p class="pp-h" style="color:#fff;margin:.1rem 0 .4rem 0">'
                f'{esc(y["name"])}</p>')
        if w is not None and len(w):
            f = D.weather_flags(w)
            nxt = f[f["date"] >= D.AS_OF].head(7)
            nxt = nxt if len(nxt) >= 3 else f.tail(7)
            now = nxt.iloc[0]
            st.html(f'<div style="display:flex;gap:26px;flex-wrap:wrap;margin:0 0 .3rem 0">'
                    f'<div><p class="pp-note" style="color:#BFD3C7;margin:0">{now["date"]:%a %b %d}</p><p style="color:#fff;font-size:1.3rem;font-weight:650;margin:0">'
                    f'{now.tmax:.0f}° / {now.tmin:.0f}°F</p></div>'
                    f'<div><p class="pp-note" style="color:#BFD3C7;margin:0">Average daily swing, next 7 days</p>'
                    f'<p style="color:{T.HAY};font-size:1.3rem;font-weight:650;margin:0">{ss.swing:.0f}°F</p></div>'
                    f'<div><p class="pp-note" style="color:#BFD3C7;margin:0">Stress days ahead</p><p style="color:#fff;font-size:1.3rem;font-weight:650;margin:0">'
                    f'{int(nxt.stress.sum())}</p></div></div>')
            fig = go.Figure()
            fig.add_scatter(x=nxt["date"], y=nxt["tmax"], mode="lines", line=dict(color="#F0A06B", width=2), hovertemplate="%{x|%a %b %d}: high %{y:.0f}°F<extra></extra>")
            fig.add_scatter(x=nxt["date"], y=nxt["tmin"], mode="lines", line=dict(color="#8FB8F0", width=2), fill="tonexty",
                            fillcolor="rgba(220,235,138,.16)", hovertemplate="%{x|%a %b %d}: low %{y:.0f}°F<extra></extra>")
            fig.update_layout(height=120, showlegend=False, margin=dict(l=4, r=4, t=4, b=4),
                              xaxis=dict(tickfont=dict(color="#BFD3C7"), gridcolor="rgba(255,255,255,.06)", tickformat="%a"),
                              yaxis=dict(tickfont=dict(color="#BFD3C7"), gridcolor="rgba(255,255,255,.08)", ticksuffix="°"))
            T.chart(fig)
            st.html(f'<p class="pp-note" style="color:#BFD3C7;margin:0 0 .4rem 0">Weather is shown for context; the risk call uses the decision '
                    f'tree\'s inputs. Source: {esc(src or "unknown")}.</p>')
        else:
            st.html('<p style="color:#DCE8E0;margin:.2rem 0 .6rem 0">Weather isn\'t synced yet.</p>')
        if st.button("Sync weather", icon=":material/cloud_sync:", key="sync_wx"):
            try:
                _sync()
                st.rerun()
            except Exception as e:
                st.warning(f"Couldn't reach the weather service ({type(e).__name__}). Check the internet connection or the yard's location under Constraints.")
