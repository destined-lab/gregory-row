"""Signal rules. One definition, used by BOTH the backtest and the live runner, so they cannot drift apart.
Rules were written down before looking at any data. Nothing here is tuned."""
import numpy as np, pandas as pd

MARKETS = {
    "SPY":     dict(kind="stock",  strat="meanrev",  tf="15Min", mins=15,  group="us_equity"),
    "QQQ":     dict(kind="stock",  strat="meanrev",  tf="15Min", mins=15,  group="us_equity"),
    "BTC/USD": dict(kind="crypto", strat="breakout", tf="1Hour", mins=60,  group="crypto"),
    "GLD":     dict(kind="stock",  strat="trend",    tf="4Hour", mins=240, group="metals"),
    "USO":     dict(kind="stock",  strat="trend",    tf="4Hour", mins=240, group="energy"),
}
MAXHOLD = {"meanrev": 26, "breakout": None, "trend": None}      # bars; None = hold until the exit signal or stop
COST = {"stock": 0.0005, "crypto": 0.003}                        # per side: slippage (+ ~0.25% crypto fee)
PLAIN = {"meanrev": "snapback: buy a sharp dip inside an uptrend, sell when it returns to normal",
         "breakout": "breakout: buy when price makes a new 24-hour high, sell on a new 12-hour low",
         "trend": "trend: hold while price is above its 50-bar average"}


def regime_from_daily(daily_close: pd.Series) -> pd.Series:
    """True on a date when the PREVIOUS completed daily close was above its 200-day average."""
    ok = (daily_close > daily_close.rolling(200).mean())
    return ok.shift(1).fillna(False)


def signals(strat, df, regime=None):
    """df: open/high/low/close indexed by bar start. Returns (enter, exit) boolean Series, evaluated at each bar's close."""
    c, h, l = df["close"], df["high"], df["low"]
    if strat == "meanrev":
        z = (c - c.rolling(20).mean()) / c.rolling(20).std()
        ok = pd.Series(True, index=df.index) if regime is None else regime
        return (z < -2.0) & ok, z > 0
    if strat == "breakout":
        return c > h.shift(1).rolling(24).max(), c < l.shift(1).rolling(12).min()
    if strat == "trend":
        s = c.rolling(50).mean()
        return c > s, c < s
    raise ValueError(strat)


def align_regime(df, regime_by_date):
    d = pd.Series(df.index.tz_convert("America/New_York").date, index=df.index)
    return d.map(regime_by_date).fillna(False).astype(bool)
