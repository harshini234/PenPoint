from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import (Column, Float, Integer, MetaData, String, Table, Text, create_engine, delete, insert, select,
                        update)

ROOT = Path(__file__).resolve().parents[2]
meta = MetaData()

T_META = Table("meta", meta, Column("key", String(64), primary_key=True), Column("value", Text))
T_YARD = Table("yard", meta, Column("yard_id", String(8), primary_key=True), Column("name", Text), Column("region", Text),
               Column("lat", Float), Column("lon", Float), Column("riders", Integer), Column("rider_hours_per_day", Float),
               Column("spare_rider_hours_per_day", Float), Column("hospital_pen_head", Float), Column("chute_hours_per_day", Float),
               Column("pen_area_m2_per_head", Float), Column("bunk_cm_per_head", Float))
T_LOTS = Table("lots", meta, Column("lot_id", String(32), primary_key=True), Column("pen", String(32)), Column("name", Text),
               Column("arrival_date", String(10)), Column("sex", String(16)), Column("buyer_risk_call", String(8)),
               Column("preconditioning", String(16)), Column("pre_arrival_vaccinated", Integer), Column("haul_hours", Float),
               Column("market_channel", String(32)), Column("origin_state", String(4)), Column("pen_area_m2", Float), Column("bunk_m", Float),
               Column("metaphylaxis_given", Integer), Column("created_at", String(32)), Column("notes", Text))
T_COWS = Table("cows", meta, Column("animal_id", String(32), primary_key=True), Column("eid", String(32)),
               Column("lot_id", String(32), index=True), Column("sex", String(16)), Column("weight_lb", Float),
               Column("pay_weight_lb", Float), Column("arrival_date", String(10)), Column("origin_state", String(4)),
               Column("seller", Text), Column("market_channel", String(32)), Column("haul_hours", Float),
               Column("preconditioning", String(16)), Column("pre_arrival_vaccinated", Integer), Column("notes", Text),
               Column("removed_reason", String(32)), Column("removed_date", String(10)))
T_EVENTS = Table("events", meta, Column("id", Integer, primary_key=True, autoincrement=True), Column("animal_id", String(32), index=True),
                 Column("lot_id", String(32), index=True), Column("date", String(10)), Column("day", Integer), Column("type", String(32)),
                 Column("detail", Text), Column("temp_c", Float), Column("source", Text), Column("drug", Text), Column("product", Text),
                 Column("drug_class", Text), Column("dose", Text), Column("route", String(16)), Column("withdrawal_days", Float),
                 Column("given_by", Text))
T_FEED = Table("feed", meta, Column("lot_id", String(32), primary_key=True), Column("day", Integer, primary_key=True),
               Column("feed_pct_bw", Float))
T_DOCS = Table("documents", meta, Column("id", Integer, primary_key=True, autoincrement=True), Column("lot_id", String(32)),
               Column("file", Text), Column("kind", Text), Column("applied", Integer), Column("uploaded_at", String(32)))
T_UPLOADS = Table("uploads", meta, Column("id", Integer, primary_key=True, autoincrement=True), Column("file", Text), Column("kind", Text),
                  Column("rows", Integer), Column("matched", Integer), Column("uploaded_at", String(32)))
T_WEATHER = Table("weather", meta, Column("date", String(10), primary_key=True), Column("tmax", Float), Column("tmin", Float),
                  Column("precip", Float), Column("wind", Float))
TABLES = {t.name: t for t in (T_META, T_YARD, T_LOTS, T_COWS, T_EVENTS, T_FEED, T_DOCS, T_UPLOADS, T_WEATHER)}


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        try:
            url = st.secrets.get("DATABASE_URL")
        except Exception:
            url = None
    if url:
        url = str(url)
        for a in ("postgres://", "postgresql://"):
            if url.startswith(a):
                return "postgresql+psycopg://" + url[len(a):]
        return url
    (ROOT / "data").mkdir(exist_ok=True)
    return f"sqlite:///{ROOT / 'data' / 'penpoint.db'}"


SCHEMA = 3


@st.cache_resource
def engine():
    url = database_url()
    e = create_engine(url, pool_pre_ping=True, future=True)
    meta.create_all(e)
    with e.begin() as c:
        r = c.execute(select(T_META.c.value).where(T_META.c.key == "schema")).first()
        if r is None or json.loads(r[0]) != SCHEMA:
            meta.drop_all(c)
            meta.create_all(c)
            c.execute(insert(T_META).values(key="schema", value=json.dumps(SCHEMA)))
    return e


def is_postgres() -> bool:
    return database_url().startswith("postgresql")


def where_label() -> str:
    url = database_url()
    if url.startswith("sqlite"):
        return f"Local SQLite file ({url.split('///', 1)[1]})"
    return "PostgreSQL at " + url.split("@")[-1].split("?")[0]


def get_meta(key, default=None):
    with engine().connect() as c:
        r = c.execute(select(T_META.c.value).where(T_META.c.key == key)).first()
    return default if r is None else json.loads(r[0])


def set_meta(key, value, conn=None):
    def _do(c):
        c.execute(delete(T_META).where(T_META.c.key == key))
        c.execute(insert(T_META).values(key=key, value=json.dumps(value, default=str)))
    if conn is not None:
        _do(conn)
    else:
        with engine().begin() as c:
            _do(c)


def version() -> int:
    return int(get_meta("version", 0))


def bump(conn):
    r = conn.execute(select(T_META.c.value).where(T_META.c.key == "version")).first()
    set_meta("version", (json.loads(r[0]) if r else 0) + 1, conn)


def read(name: str) -> pd.DataFrame:
    t = TABLES[name]
    with engine().connect() as c:
        df = pd.read_sql(select(t), c)
    return df


def _clean(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        return v.item()
    return v


def records(df_or_rows):
    rows = df_or_rows.to_dict("records") if isinstance(df_or_rows, pd.DataFrame) else list(df_or_rows)
    return [{k: _clean(v) for k, v in r.items()} for r in rows]


def write(fn):
    with engine().begin() as c:
        out = fn(c)
        bump(c)
    return out


def insert_rows(conn, name, rows):
    rows = records(rows)
    if rows:
        cols = {c.name for c in TABLES[name].columns}
        conn.execute(insert(TABLES[name]), [{k: v for k, v in r.items() if k in cols} for r in rows])


def update_rows(conn, name, key_col, key, values: dict):
    t = TABLES[name]
    conn.execute(update(t).where(t.c[key_col] == key).values(**{k: _clean(v) for k, v in values.items()}))


def delete_rows(conn, name, col=None, value=None):
    t = TABLES[name]
    conn.execute(delete(t) if col is None else delete(t).where(t.c[col] == value))


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")
