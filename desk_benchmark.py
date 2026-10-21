"""Buy-and-hold benchmark book. VIRTUAL: no orders are placed, so it can never touch the desk's paper positions.
$50 split equally across the original five markets on the inception date, then simply held. This is the bar the desk
has to beat. Writes benchmark.json (inception and entry prices are fixed on the first run and never change)."""
import datetime as dt, json, os
import pandas as pd
import risk
from dlib import Broker, verify_risk_lock

LEGS = {"SPY": "stock", "QQQ": "stock", "GLD": "stock", "USO": "stock", "BTC/USD": "crypto"}
OUT = "benchmark.json"


def closes(b, sym, kind, start):
    if kind == "crypto":
        df = b.intraday(sym, dict(kind="crypto", tf="1Day"), start)
        s = df["close"]; s.index = s.index.tz_convert("America/New_York").date
        return s
    return b.daily_close(sym, start)


def main():
    verify_risk_lock()
    b = Broker(os.environ["ALPACA_KEY"], os.environ["ALPACA_SECRET"])
    bm = json.load(open(OUT)) if os.path.exists(OUT) else None
    start = dt.date.fromisoformat(bm["inception"]) if bm else dt.date.today() - dt.timedelta(days=7)
    start_dt = dt.datetime.combine(start - dt.timedelta(days=7), dt.time(), tzinfo=dt.timezone.utc)
    px = {s: closes(b, s, k, start_dt) for s, k in LEGS.items()}
    if not bm:
        each = risk.CAPITAL / len(LEGS)
        legs = {s: dict(entry=float(px[s].iloc[-1]), units=each / float(px[s].iloc[-1])) for s in LEGS}
        bm = dict(inception=dt.date.today().isoformat(), capital=risk.CAPITAL, legs=legs)
    frame = pd.DataFrame({s: px[s] for s in LEGS}).sort_index().ffill()
    frame = frame[frame.index >= dt.date.fromisoformat(bm["inception"])].dropna()
    curve = [[str(d), round(sum(row[s] * bm["legs"][s]["units"] for s in LEGS), 4)] for d, row in frame.iterrows()]
    if not curve:
        curve = [[bm["inception"], bm["capital"]]]
    last = {s: float(px[s].iloc[-1]) for s in LEGS}
    for s in LEGS:
        bm["legs"][s]["last"] = round(last[s], 4)
        bm["legs"][s]["value"] = round(last[s] * bm["legs"][s]["units"], 4)
    bm.update(curve=curve, equity=round(sum(l["value"] for l in bm["legs"].values()), 4),
              asof=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    json.dump(bm, open(OUT, "w"), indent=1)
    print(f"benchmark ${bm['equity']:.2f} since {bm['inception']}")


if __name__ == "__main__":
    main()
