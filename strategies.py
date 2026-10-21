"""Signal rules. One definition, used by BOTH the backtest and the live runner, so they cannot drift apart.
Rules were written down before looking at any data. Nothing here is tuned."""
import numpy as np, pandas as pd

MARKETS = {
    "SPY":     dict(kind="stock",  strat="meanrev",  tf="15Min", mins=15,  group="us_equity"),
    "QQQ":     dict(kind="stock",  strat="meanrev",  tf="15Min", mins=15,  group="us_equity"),
    "BTC/USD": dict(kind="crypto", strat="breakout", tf="1Hour", mins=60,  group="crypto"),
    "GLD":     dict(kind="stock",  strat="trend",    tf="4Hour", mins=240, group="metals"),
    "USO":     dict(kind="stock",  strat="trend",    tf="4Hour", mins=240, group="energy"),
    # Round 2 (Oct 21, 2026). Written before any data was pulled for them. Daily bars, low frequency. Untuned.
    "DIA":     dict(kind="stock",  strat="turn_of_month", tf="1Day", mins=1440, group="us_equity", years=10),
    "IWM":     dict(kind="stock",  strat="rsi2_pullback", tf="1Day", mins=1440, group="us_equity", years=10),
}
MAXHOLD = {"meanrev": 26, "breakout": None, "trend": None, "turn_of_month": 6, "rsi2_pullback": 10}      # bars; None = hold until the exit signal or stop
COST = {"stock": 0.0005, "crypto": 0.003}                        # per side: slippage (+ ~0.25% crypto fee)
PLAIN = {"meanrev": "snapback: buy a sharp dip inside an uptrend, sell when it returns to normal",
         "breakout": "breakout: buy when price makes a new 24-hour high, sell on a new 12-hour low",
         "trend": "trend: hold while price is above its 50-bar average",
         "turn_of_month": "turn of month: buy into the last trading day of the month, sell after the 3rd trading day of the next",
         "rsi2_pullback": "pullback: buy a 2-day RSI under 10 while above the 200-day average, sell on a close above the 5-day average"}


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
    if strat == "turn_of_month":
        # Month-end flows (pay, pensions, index rebalancing). Weekday calendar, no holiday table: same code live and backtest.
        d = pd.DatetimeIndex(df.index.tz_convert("America/New_York").date)
        last = d + pd.offsets.BMonthEnd(0)
        left = np.busday_count((d + pd.Timedelta(days=1)).values.astype("datetime64[D]"),
                               (last + pd.Timedelta(days=1)).values.astype("datetime64[D]"))
        nth = pd.Series(1, index=df.index).groupby([d.year, d.month]).cumsum().values
        return pd.Series(left == 1, index=df.index), pd.Series(nth == 3, index=df.index)
    if strat == "rsi2_pullback":
        # Connors-style short pullback inside a long uptrend. Parameters are the published ones, not fitted here.
        dlt = c.diff()
        up = dlt.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
        dn = (-dlt.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
        rsi = 100 - 100 / (1 + up / dn.replace(0, np.nan))
        return (rsi < 10) & (c > c.rolling(200).mean()), c > c.rolling(5).mean()
    if strat == "trend":
        s = c.rolling(50).mean()
        return c > s, c < s
    raise ValueError(strat)


def align_regime(df, regime_by_date):
    d = pd.Series(df.index.tz_convert("America/New_York").date, index=df.index)
    return d.map(regime_by_date).fillna(False).astype(bool)
