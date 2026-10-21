import datetime as dt, hashlib, os
import pandas as pd, requests
from bot import Alpaca as _Base
import risk

DATA = "https://data.alpaca.markets"
NY = "America/New_York"


def verify_risk_lock():
    want = open("risk.sha256").read().strip()
    got = hashlib.sha256(open("risk.py", "rb").read()).hexdigest()
    if want != got:
        raise SystemExit("risk.py does not match risk.sha256. Risk rules are locked. A human must approve changes.")
    assert risk.PAPER_ONLY and "paper-api" in risk.TRADE_URL


class Broker(_Base):
    def clock(self):
        return self._req("GET", f"{risk.TRADE_URL}/clock")

    def account(self):
        a = self._req("GET", f"{risk.TRADE_URL}/account")
        return dict(equity=float(a["equity"]), cash=float(a["cash"]))

    def positions(self):
        out = {}
        for p in self._req("GET", f"{risk.TRADE_URL}/positions") or []:
            out[p["symbol"]] = dict(qty=float(p["qty"]), entry=float(p["avg_entry_price"]), upl=float(p["unrealized_pl"]),
                                    price=float(p["current_price"]))
        return out

    def _bars(self, url, params, key):
        rows, token = [], None
        while True:
            q = dict(params)
            if token:
                q["page_token"] = token
            j = self._req("GET", url, params=q)
            b = j.get("bars") or {}
            rows += (b.get(key) or []) if isinstance(b, dict) else b
            token = j.get("next_page_token")
            if not token:
                break
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close"])
        df = pd.DataFrame(rows)
        df.index = pd.to_datetime(df["t"], utc=True)
        return df[["o", "h", "l", "c"]].rename(columns=dict(o="open", h="high", l="low", c="close")).sort_index()

    def intraday(self, sym, m, start):
        s = start.isoformat()
        if m["kind"] == "crypto":
            df = self._bars(f"{DATA}/v1beta3/crypto/us/bars", dict(symbols=sym, timeframe=m["tf"], start=s, limit=10000), sym)
        else:
            df = self._bars(f"{DATA}/v2/stocks/{sym}/bars", dict(timeframe=m["tf"], start=s, limit=10000, feed="iex", adjustment="all"), None)
            if m["tf"] == "15Min" and len(df):          # regular session only
                t = df.index.tz_convert(NY)
                mins = t.hour * 60 + t.minute
                df = df[(mins >= 570) & (mins < 960)]
        return df

    def daily_close(self, sym, start):
        df = self._bars(f"{DATA}/v2/stocks/{sym}/bars", dict(timeframe="1Day", start=start.isoformat(), limit=10000, feed="iex", adjustment="all"), None)
        s = df["close"]
        s.index = s.index.tz_convert(NY).date
        return s

    def buy(self, sym, notional, crypto):
        o = self._req("POST", f"{risk.TRADE_URL}/orders", json=dict(symbol=sym, notional=f"{notional:.2f}", side="buy",
                      type="market", time_in_force="gtc" if crypto else "day"))
        return o["id"]

    def close_pos(self, sym):
        o = self._req("DELETE", f"{risk.TRADE_URL}/positions/{sym.replace('/', '')}")
        return o.get("id", "") if isinstance(o, dict) else ""


def drop_incomplete(df, mins, now=None):
    now = now or pd.Timestamp.now(tz="UTC")
    if len(df) and df.index[-1] + pd.Timedelta(minutes=mins) > now:
        return df.iloc[:-1]
    return df
