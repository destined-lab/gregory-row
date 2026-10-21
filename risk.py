"""LOCKED RISK RULES. Strategy code and any automated improvement loop may NOT edit this file.
desk.py refuses to run if this file's hash does not match risk.sha256. To change a rule, a human edits this file
and regenerates the hash:  python -c "import hashlib;print(hashlib.sha256(open('risk.py','rb').read()).hexdigest())" > risk.sha256
"""
PAPER_ONLY = True
TRADE_URL = "https://paper-api.alpaca.markets/v2"   # no live URL exists anywhere in this project
CAPITAL = 50.0          # virtual book. Real money stays untouched until Feb 16, 2027
STOP_PCT = 0.01         # hard 1% stop on every trade. No exceptions
SLEEVE = 0.20           # each market gets 20% of the book (5 markets, no leverage)
MAX_DRAWDOWN = 0.10     # book down 10% from its peak: close everything and halt until a human resets it
LONG_ONLY = True
CORR_GROUPS = {"us_equity": ["SPY", "QQQ"]}   # at most ONE open position per group (no doubled-up risk)
PAUSE_LOOKBACK, PAUSE_LOSS, PAUSE_DAYS = 8, -0.04, 7   # last 8 trades down 4%: that market sits out 7 days


def sleeve_notional(book_equity):
    return round(max(0.0, min(CAPITAL, book_equity)) * SLEEVE, 2)


def stopped(entry_price, price):
    return price <= entry_price * (1 - STOP_PCT)
