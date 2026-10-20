"""Gregory Row paper bot. PAPER ONLY. Rule: hold SPY while the last completed daily close is above its 200-day average.
Runs once per weekday shortly after the open, acts on the last COMPLETED daily bar, logs to ledger.csv, rebuilds docs/index.html.
"""
import os, sys, csv, datetime as dt
from zoneinfo import ZoneInfo
import requests, pandas as pd

CFG = dict(symbol="SPY", sma=200, stop_pct=0.05, risk_pct=0.01, capital=50.0)
TRADE = "https://paper-api.alpaca.markets/v2"   # hard-coded paper. There is no live switch on purpose.
DATA = "https://data.alpaca.markets/v2"
ET = ZoneInfo("America/New_York")
LEDGER, BOARD = "ledger.csv", "docs/index.html"
COLS = ["run_date", "bar_date", "close", "sma", "signal", "action", "notional", "order_id",
        "position_qty", "entry_price", "stop_price", "unrealized_pl", "account_equity", "virtual_equity"]


class Alpaca:
    def __init__(self, key, secret):
        self.h = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}

    def _req(self, method, url, **kw):
        r = requests.request(method, url, headers=self.h, timeout=30, **kw)
        if r.status_code == 404 and "positions" in url:
            return None
        r.raise_for_status()
        return r.json() if r.text else {}

    def clock(self):
        return self._req("GET", f"{TRADE}/clock")

    def account(self):
        a = self._req("GET", f"{TRADE}/account")
        return dict(equity=float(a["equity"]), cash=float(a["cash"]))

    def position(self, sym):
        p = self._req("GET", f"{TRADE}/positions/{sym}")
        if not p:
            return None
        return dict(qty=float(p["qty"]), entry=float(p["avg_entry_price"]), upl=float(p["unrealized_pl"]))

    def bars(self, sym, before):
        start = (before - dt.timedelta(days=420)).isoformat()
        out, token = [], None
        while True:
            q = dict(timeframe="1Day", start=start, limit=1000, feed="iex", adjustment="all")
            if token:
                q["page_token"] = token
            j = self._req("GET", f"{DATA}/stocks/{sym}/bars", params=q)
            out += j.get("bars") or []
            token = j.get("next_page_token")
            if not token:
                break
        df = pd.DataFrame(out)
        df["d"] = pd.to_datetime(df["t"]).dt.tz_convert(ET).dt.date
        df = df.set_index("d")
        return df[df.index < before][["o", "c"]].rename(columns={"o": "open", "c": "close"})

    def buy(self, sym, notional):
        o = self._req("POST", f"{TRADE}/orders", json=dict(symbol=sym, notional=f"{notional:.2f}",
                      side="buy", type="market", time_in_force="day"))
        return o["id"]

    def close(self, sym):
        o = self._req("DELETE", f"{TRADE}/positions/{sym}")
        return o.get("id", "") if isinstance(o, dict) else ""


def read_ledger():
    if not os.path.exists(LEDGER):
        return []
    with open(LEDGER, newline="") as f:
        return list(csv.DictReader(f))


def run(broker, today, check_clock=True):
    rows = read_ledger()
    if any(r["run_date"] == str(today) for r in rows):
        print("already ran today"); return
    if check_clock and not broker.clock()["is_open"]:
        print("market closed, nothing to do"); return
    c = CFG
    bars = broker.bars(c["symbol"], today)
    if len(bars) < c["sma"] + 1:
        raise RuntimeError(f"only {len(bars)} bars, need {c['sma']+1}")
    close = float(bars["close"].iloc[-1]); sma = float(bars["close"].tail(c["sma"]).mean())
    bar_date = bars.index[-1]
    long_ok = close > sma
    pos, acct = broker.position(c["symbol"]), broker.account()
    action, notional, oid = "hold", 0.0, ""
    if pos is None and long_ok:
        base = min(c["capital"], acct["equity"])
        notional = round(min(base * c["risk_pct"] / c["stop_pct"], acct["cash"]), 2)
        if notional >= 1:
            oid = broker.buy(c["symbol"], notional); action = "buy"
    elif pos is not None and (not long_ok or close <= pos["entry"] * (1 - c["stop_pct"])):
        oid = broker.close(c["symbol"]); action = "exit_signal" if not long_ok else "exit_stop"
    first_eq = float(rows[0]["account_equity"]) if rows else acct["equity"]
    row = dict(run_date=today, bar_date=bar_date, close=round(close, 2), sma=round(sma, 2),
               signal="long" if long_ok else "flat", action=action, notional=notional, order_id=oid,
               position_qty=pos["qty"] if pos and action == "hold" else 0,
               entry_price=round(pos["entry"], 2) if pos and action == "hold" else "",
               stop_price=round(pos["entry"] * (1 - c["stop_pct"]), 2) if pos and action == "hold" else "",
               unrealized_pl=pos["upl"] if pos else 0,
               account_equity=round(acct["equity"], 2),
               virtual_equity=round(c["capital"] + acct["equity"] - first_eq, 2))
    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a", newline="") as f:
        w = csv.DictWriter(f, COLS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(row)
    build_board()


def build_board():
    import json
    rows = read_ledger()
    tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "hub_template.html")).read()
    data = json.dumps(dict(rows=rows, capital=CFG["capital"])).replace("</", "<\\/")
    os.makedirs("docs", exist_ok=True)
    with open(BOARD, "w") as f:
        f.write(tpl.replace("__DATA__", data))


if __name__ == "__main__":
    key, sec = os.environ.get("ALPACA_KEY"), os.environ.get("ALPACA_SECRET")
    if not key or not sec:
        sys.exit("Set ALPACA_KEY and ALPACA_SECRET (paper keys).")
    run(Alpaca(key, sec), dt.datetime.now(ET).date())
