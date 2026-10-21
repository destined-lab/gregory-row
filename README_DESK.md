# Gregory Row desk (paper only)

Five markets, one rule each, written down before any data was looked at:
- SPY, QQQ: snapback on 15-minute candles. Buy a sharp dip (price 2 standard deviations under its 20-bar average) only while the market is above its 200-day average. Sell when price returns to normal, after 26 bars, or at the stop.
- BTC/USD: breakout on 1-hour candles. Buy a new 24-hour high. Sell on a new 12-hour low or at the stop.
- GLD (gold), USO (oil): trend on 4-hour candles. Hold while price is above its 50-bar average.

Locked rules (risk.py, hash-checked, nothing automated may edit it): 1% hard stop, each market gets 20% of a $50 virtual book (no leverage),
long only, one open position per correlated group (SPY and QQQ never both), book down 10% from its peak = close everything and halt,
last 8 trades of a market down 4% = that market sits out 7 days.

The gate: desk_backtest.py tests each market with the same signal code the live desk uses. A market may trade only if it has 30+ trades,
is profitable in both halves of history, and earns at least as much per unit of worst drawdown as simply holding it. approved.json holds the verdict.
Failures are written to failures.csv with an autopsy of the worst trades in autopsy.md. A failure is logged, never patched to pass.

Limits worth knowing: stops are checked each run (15 min stocks, 1 hour crypto), not tick by tick. GitHub schedules can run late. Paper fills are optimistic.
