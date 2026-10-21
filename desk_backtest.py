"""Backtest every market with the SAME signal code the live desk uses, then decide which markets may trade.
Writes approved.json (the gate), failures.csv (every failed idea, kept forever) and autopsy.md (worst trades of failures).
Gate (written before seeing results): >= 30 trades, positive total return in BOTH halves, and return per unit of worst
drawdown at least as good as buy and hold. No parameter is tuned. A failure is logged, not patched."""
import os, sys, json, csv, datetime as dt
import numpy as np, pandas as pd
import risk, strategies as S
from dlib import Broker, verify_risk_lock, NY


def simulate(df, strat, regime, cost):
    o, h, l, c = (df[k].values for k in ("open", "high", "low", "close"))
    en, ex = (x.fillna(False).values for x in S.signals(strat, df, regime))
    n, maxhold = len(df), S.MAXHOLD[strat]
    r = np.zeros(n); trades = []; pos = False; entry = 0.0; ei = 0; pend = None; held = 0
    for i in range(1, n):
        ret = 0.0
        def stop_hit(px):
            return l[i] <= px * (1 - risk.STOP_PCT)
        if pend == "sell" and pos:
            fill = o[i] * (1 - cost); ret = fill / c[i - 1] - 1; pos = False
            trades.append((df.index[ei], df.index[i], entry, fill, "signal"))
        elif pos:
            if stop_hit(entry):
                fill = min(o[i], entry * (1 - risk.STOP_PCT)) * (1 - cost); ret = fill / c[i - 1] - 1; pos = False
                trades.append((df.index[ei], df.index[i], entry, fill, "stop"))
            else:
                ret = c[i] / c[i - 1] - 1
        if pend == "buy" and not pos:
            entry = o[i] * (1 + cost); pos = True; ei = i; held = 0
            if stop_hit(entry):
                fill = min(o[i], entry * (1 - risk.STOP_PCT)) * (1 - cost); ret = fill / entry - 1; pos = False
                trades.append((df.index[ei], df.index[i], entry, fill, "stop"))
            else:
                ret = c[i] / entry - 1
        pend = None
        if pos:
            held += 1
            if ex[i] or (maxhold and held >= maxhold):
                pend = "sell"
        elif en[i]:
            pend = "buy"
        r[i] = ret
    if pos:
        trades.append((df.index[ei], df.index[-1], entry, c[-1], "open"))
    return pd.Series(r, index=df.index), trades


def stats(r):
    eq = (1 + r).cumprod()
    return float(eq.iloc[-1] - 1), float((eq / eq.cummax() - 1).min())


def judge(r, bh, trades):
    why = []
    tot, dd = stats(r); btot, bdd = stats(bh)
    mid = len(r) // 2
    t1, _ = stats(r.iloc[:mid]); t2, _ = stats(r.iloc[mid:])
    if len(trades) < 30: why.append(f"only {len(trades)} trades (need 30)")
    if tot <= 0: why.append("negative total return")
    if t1 <= 0 or t2 <= 0: why.append(f"not profitable in both halves ({t1:.1%} / {t2:.1%})")
    if tot / abs(dd or 1e-9) < btot / abs(bdd or 1e-9): why.append("less return per unit of drawdown than buy and hold")
    return why, dict(total=tot, maxdd=dd, bh_total=btot, bh_maxdd=bdd, trades=len(trades), half1=t1, half2=t2)


def load(b, sym, m, years):
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(365 * years))
    df = b.intraday(sym, m, start)
    reg = None
    if m["strat"] == "meanrev":
        daily = b.daily_close(sym, start - dt.timedelta(days=330))
        reg = S.align_regime(df, S.regime_from_daily(daily).to_dict())
    return df, reg


def main(frames=None):
    verify_risk_lock()
    b = None if frames else Broker(os.environ["ALPACA_KEY"], os.environ["ALPACA_SECRET"])
    approved, fails, autopsy = {}, [], ["# Autopsy of failed ideas\n"]
    today = dt.date.today().isoformat()
    for sym, m in S.MARKETS.items():
        try:
            df, reg = frames[sym] if frames else load(b, sym, m, 3 if m["tf"] == "15Min" else 5)
        except Exception as e:
            print(sym, "data error:", e); approved[sym] = dict(ok=False, why=["data error"]); continue
        if len(df) < 300:
            print(sym, "not enough bars:", len(df)); approved[sym] = dict(ok=False, why=["not enough history"]); continue
        r, trades = simulate(df, m["strat"], reg, S.COST[m["kind"]])
        bh = df["close"].pct_change().fillna(0)
        why, st = judge(r, bh, trades)
        ok = not why
        approved[sym] = dict(ok=ok, why=why, asof=today, **{k: round(v, 4) if isinstance(v, float) else v for k, v in st.items()})
        print(f"{sym:8s} {m['strat']:9s} {'PASS' if ok else 'FAIL'}  rule {st['total']:7.1%} dd {st['maxdd']:7.1%} | hold {st['bh_total']:7.1%} dd {st['bh_maxdd']:7.1%} | trades {st['trades']}", "; ".join(why))
        if not ok:
            fails.append([today, sym, m["strat"], "; ".join(why), round(st["total"], 4), round(st["bh_total"], 4)])
            autopsy.append(f"\n## {sym} ({m['strat']}): {'; '.join(why)}\nWorst 5 trades:\n")
            for t in sorted(trades, key=lambda t: t[3] / t[2])[:5]:
                autopsy.append(f"- in {t[0]:%Y-%m-%d %H:%M} out {t[1]:%Y-%m-%d %H:%M}  {t[3]/t[2]-1:+.2%}  ({t[4]})\n")
    json.dump(approved, open("approved.json", "w"), indent=1)
    new = not os.path.exists("failures.csv")
    with open("failures.csv", "a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(["date", "market", "strategy", "why_failed", "rule_total", "buyhold_total"])
        w.writerows(fails)
    open("autopsy.md", "w").write("".join(autopsy))
    print("approved:", [k for k, v in approved.items() if v["ok"]] or "none")


if __name__ == "__main__":
    main()
