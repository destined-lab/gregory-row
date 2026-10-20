"""Backtest of the same rule on daily bars. Next-day open fills, 0.05% slippage per side, 5% close-based stop.
Usage: ALPACA_KEY=... ALPACA_SECRET=... python backtest.py   (pulls ~9 years of SPY from Alpaca IEX)
       python backtest.py bars.csv                            (csv with date,open,close)
No parameter is tuned: 200 days and 5% were set before looking at data.
"""
import os, sys, datetime as dt
import pandas as pd, numpy as np
import requests
from bot import CFG, DATA, ET, Alpaca

SLIP = 0.0005

def load():
    if len(sys.argv) > 1:
        return pd.read_csv(sys.argv[1], parse_dates=["date"], index_col="date")[["open", "close"]]
    a = Alpaca(os.environ["ALPACA_KEY"], os.environ["ALPACA_SECRET"])
    out, token = [], None
    while True:
        q = dict(timeframe="1Day", start="2016-06-01", limit=10000, feed="iex", adjustment="all")
        if token: q["page_token"] = token
        j = a._req("GET", f"{DATA}/stocks/{CFG['symbol']}/bars", params=q)
        out += j.get("bars") or []; token = j.get("next_page_token")
        if not token: break
    df = pd.DataFrame(out); df.index = pd.to_datetime(df["t"]).dt.tz_convert(ET).dt.tz_localize(None).dt.normalize()
    return df[["o", "c"]].rename(columns={"o": "open", "c": "close"})

def simulate(df):
    c, o = df["close"].values, df["open"].values
    sma = pd.Series(c).rolling(CFG["sma"]).mean().values
    eq, rets, inpos, entry, want = 1.0, [], False, 0.0, None
    trades = 0
    for i in range(1, len(c)):
        r = 0.0
        if np.isnan(sma[i - 1]): rets.append(0.0); continue
        if want == "buy" and not inpos:
            inpos, entry, trades = True, o[i] * (1 + SLIP), trades + 1
            r = c[i] / entry - 1
        elif want == "sell" and inpos:
            r = (o[i] * (1 - SLIP)) / c[i - 1] - 1; inpos = False
        elif inpos:
            r = c[i] / c[i - 1] - 1
        want = None
        long_ok = c[i] > sma[i]
        if not inpos and long_ok: want = "buy"
        if inpos and (not long_ok or c[i] <= entry * (1 - CFG["stop_pct"])): want = "sell"
        rets.append(r)
    return pd.Series(rets, index=df.index[1:]), trades

def stats(r):
    eq = (1 + r).cumprod(); yrs = len(r) / 252
    dd = (eq / eq.cummax() - 1).min()
    return eq.iloc[-1] - 1, eq.iloc[-1] ** (1 / yrs) - 1, dd

df = load()
r, trades = simulate(df)
bh = df["close"].pct_change().dropna().reindex(r.index).fillna(0)
for name, x in (("Rule", r), ("Buy and hold", bh)):
    t, cagr, dd = stats(x)
    print(f"{name:13s} total {t:7.1%}  per year {cagr:6.1%}  worst drawdown {dd:7.1%}")
print(f"Trades: {trades}  Days: {len(r)}  Range: {df.index[0].date()} to {df.index[-1].date()}")
folds = [(r.iloc[i:i + 60], bh.iloc[i:i + 60]) for i in range(0, len(r) - 59, 60)]
pos = sum((1 + a).prod() - 1 > 0 for a, b in folds)
beat = sum((1 + a).prod() > (1 + b).prod() for a, b in folds)
worst = min((1 + a).prod() - 1 for a, b in folds)
print(f"60-day folds: {len(folds)}  positive: {pos}  beat buy and hold: {beat}  worst fold: {worst:.1%}")
print("Verdict rule: if it does not beat buy and hold on drawdown OR return, say so. Do not retune until it passes.")
