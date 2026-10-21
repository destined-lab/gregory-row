"""Gregory Row desk. PAPER ONLY. Runs on a schedule, trades only the markets that passed the backtest gate (approved.json),
under the locked rules in risk.py. Usage: python desk.py stock   |   python desk.py crypto   |   python desk.py all"""
import os, sys, csv, json, datetime as dt
import pandas as pd
import risk, strategies as S
from dlib import Broker, verify_risk_lock, drop_incomplete

LEDGER, TRADES, STATE = "desk_ledger.csv", "desk_trades.csv", "state.json"
LCOLS = ["ts", "market", "strategy", "price", "signal", "action", "notional", "order_id", "note"]
TCOLS = ["ts_close", "market", "entry", "exit", "ret", "reason"]


def jload(p, d):
    return json.load(open(p)) if os.path.exists(p) else d


def append(path, cols, row):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, cols)
        if new: w.writeheader()
        w.writerow(row)


def read_trades():
    if not os.path.exists(TRADES): return []
    with open(TRADES, newline="") as f: return list(csv.DictReader(f))


def book_equity(trades, positions):
    sleeve = risk.CAPITAL * risk.SLEEVE
    return risk.CAPITAL + sum(float(t["ret"]) * sleeve for t in trades) + sum(p["upl"] for p in positions.values())


def log(now, sym, strat, price, sig, action, notional=0, oid="", note=""):
    row = dict(ts=now.isoformat(timespec="seconds"), market=sym, strategy=strat, price=round(price, 4) if price else "",
               signal=sig, action=action, notional=notional, order_id=oid, note=note)
    if action not in ("wait", "hold"): append(LEDGER, LCOLS, row)   # the ledger is actions only; waiting is not logged
    print(row)


def run(b, which="all", now=None, check_clock=True):
    verify_risk_lock()
    now = now or pd.Timestamp.now(tz="UTC")
    approved, st = jload("approved.json", {}), jload(STATE, {"peak": risk.CAPITAL, "halted": False, "last_bar": {}, "entry": {}, "pause": {}})
    trades = read_trades(); pos = b.positions()
    eq = book_equity(trades, pos); st["peak"] = max(st["peak"], eq)
    if st["halted"] or eq <= st["peak"] * (1 - risk.MAX_DRAWDOWN):
        if not st["halted"]:
            for s in list(pos):
                b.close_pos(s); log(now, s, "kill_switch", pos[s]["price"], "halt", "close_all", note=f"book {eq:.2f} vs peak {st['peak']:.2f}")
            st["halted"] = True
        print("HALTED: book is 10% below its peak. A human must reset state.json to resume."); json.dump(st, open(STATE, "w"), indent=1); return
    stock_open = (not check_clock) or b.clock()["is_open"]
    for sym, m in S.MARKETS.items():
        if which != "all" and m["kind"] != which: continue
        if not approved.get(sym, {}).get("ok"): continue
        if m["kind"] == "stock" and not stock_open: continue
        key = sym.replace("/", "")
        until = st["pause"].get(sym)
        if until and now < pd.Timestamp(until): continue
        start = (now - pd.Timedelta(days={"15Min": 70, "1Hour": 14, "4Hour": 120, "1Day": 420}[m["tf"]])).to_pydatetime()
        df = drop_incomplete(b.intraday(sym, m, start), m["mins"], now)
        if len(df) < 60: print(sym, "not enough bars"); continue
        bar = df.index[-1].isoformat()
        if st["last_bar"].get(sym) == bar: continue                      # this bar was already handled
        reg = None
        if m["strat"] == "meanrev":
            reg = S.align_regime(df, S.regime_from_daily(b.daily_close(sym, (now - pd.Timedelta(days=420)).date())).to_dict())
        en, ex = S.signals(m["strat"], df, reg)
        price, p = float(df["close"].iloc[-1]), pos.get(key)
        sig = "enter" if bool(en.iloc[-1]) else ("exit" if bool(ex.iloc[-1]) else "none")
        if p:
            held = int((df.index > pd.Timestamp(st["entry"].get(sym, bar))).sum())
            mh = S.MAXHOLD[m["strat"]]
            why = "stop" if risk.stopped(p["entry"], price) else ("signal" if bool(ex.iloc[-1]) else ("time" if mh and held >= mh else ""))
            if why:
                oid = b.close_pos(sym); ret = price / p["entry"] - 1 - 2 * S.COST[m["kind"]]
                append(TRADES, TCOLS, dict(ts_close=now.isoformat(timespec="seconds"), market=sym, entry=round(p["entry"], 4), exit=round(price, 4), ret=round(ret, 5), reason=why))
                log(now, sym, m["strat"], price, sig, f"exit_{why}", oid=oid); st["entry"].pop(sym, None)
                mine = [float(t["ret"]) for t in read_trades() if t["market"] == sym][-risk.PAUSE_LOOKBACK:]
                tot = 1.0
                for x in mine: tot *= 1 + x
                if len(mine) >= risk.PAUSE_LOOKBACK and tot - 1 < risk.PAUSE_LOSS:
                    st["pause"][sym] = (now + pd.Timedelta(days=risk.PAUSE_DAYS)).isoformat()
                    log(now, sym, m["strat"], price, "pause", "pause_7d", note=f"last {len(mine)} trades {tot-1:.1%}")
            else:
                log(now, sym, m["strat"], price, sig, "hold", note=f"uPL {p['upl']:.2f}")
        elif bool(en.iloc[-1]):
            grp = next((g for g, mem in risk.CORR_GROUPS.items() if sym in mem), None)
            if grp and any(x.replace("/", "") in pos for x in risk.CORR_GROUPS[grp] if x != sym):
                log(now, sym, m["strat"], price, sig, "skip", note="correlation filter: a sibling is already long"); st["last_bar"][sym] = bar; continue
            mine = [x for x, mm in S.MARKETS.items() if mm["group"] == m["group"] and x != sym]
            if any(x.replace("/", "") in pos for x in mine):     # stricter than risk.py: one long per strategy group too
                log(now, sym, m["strat"], price, sig, "skip", note="group filter: a sibling is already long"); st["last_bar"][sym] = bar; continue
            if len(pos) >= round(1 / risk.SLEEVE):                # never more sleeves open than the book holds
                log(now, sym, m["strat"], price, sig, "skip", note="book full"); st["last_bar"][sym] = bar; continue
            notional = risk.sleeve_notional(eq)
            if notional >= 1:
                oid = b.buy(sym, notional, m["kind"] == "crypto"); st["entry"][sym] = bar
                log(now, sym, m["strat"], price, sig, "buy", notional, oid)
        else:
            log(now, sym, m["strat"], price, sig, "wait")
        st["last_bar"][sym] = bar
    json.dump(st, open(STATE, "w"), indent=1)


if __name__ == "__main__":
    k, s = os.environ.get("ALPACA_KEY"), os.environ.get("ALPACA_SECRET")
    if not k or not s: sys.exit("Set ALPACA_KEY and ALPACA_SECRET (paper keys).")
    run(Broker(k, s), sys.argv[1] if len(sys.argv) > 1 else "all")
