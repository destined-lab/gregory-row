# Gregory Row paper bot (paper only)

Rule: hold SPY while the last completed daily close is above its 200-day average. Exit when it drops below, or when the close is 5% under the entry. Size = 1% of a $50 account risked per trade, so about $10 per position. It cannot touch real money: the paper URL is hard-coded.

Files: bot.py (daily run), backtest.py (history test), ledger.csv (every day logged), docs/index.html (status board), .github/workflows/daily.yml (schedule).

Setup (once):
1. alpaca.markets, make an account, open Paper Trading, generate API keys. Reset the paper account to $50 if it lets you. If not, the bot still sizes from $50.
2. New GitHub repo, upload these files. Settings, Secrets and variables, Actions: add ALPACA_KEY and ALPACA_SECRET.
3. Actions tab, run "daily-paper-bot" once by hand to test.
4. Optional board: Settings, Pages, deploy from /docs (needs a public repo; it only shows paper trades).

Before trusting it: run backtest.py. If the rule does not beat buy-and-hold on return or drawdown, it does not go live. Do not retune until it passes.

Feb 16, 2027 or later, when you can open a real account: build a separate live version and review it first. Do not flip this one.
