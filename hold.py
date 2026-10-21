"""The Hold: a live PAPER buy-and-hold book the system places by itself.
$10 each into five sleeves, bought once, then held. Twin tickers on purpose, so it never shares a symbol with a desk rule
(desk: SPY QQQ GLD USO BTC/USD DIA IWM). Runs inside every desk job; buys only what it does not already own.
State: hold.json (what was bought, when, order id). Paper only, through the same locked risk.py checks as the desk."""
import datetime as dt, json, os
import risk
from dlib import Broker, verify_risk_lock

HOLD = {"VOO": "stock", "QQQM": "stock", "IAU": "stock", "BNO": "stock", "ETH/USD": "crypto"}
EACH = 10.0
OUT = "hold.json"


def main():
    verify_risk_lock()
    b = Broker(os.environ["ALPACA_KEY"], os.environ["ALPACA_SECRET"])
    st = json.load(open(OUT)) if os.path.exists(OUT) else {"each": EACH, "legs": {}}
    held = b.positions()
    stock_open = b.clock()["is_open"]
    for sym, kind in HOLD.items():
        key = sym.replace("/", "")
        if sym in st["legs"] or key in held:
            continue
        if kind == "stock" and not stock_open:
            print(sym, "waiting for the stock market to open"); continue
        try:
            oid = b.buy(sym, EACH, kind == "crypto")
            st["legs"][sym] = dict(order_id=oid, ts=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), notional=EACH)
            print(sym, "bought", EACH, oid)
        except Exception as e:
            print(sym, "order failed, will retry next run:", e)
    json.dump(st, open(OUT, "w"), indent=1)


if __name__ == "__main__":
    main()
