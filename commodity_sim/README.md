# Commodity Desk

A commodity trading simulator with **simulated prices**, an **analysis panel with Buy / Sell / Hold signals**, **paper trading** and a **strategy backtester**.
Nine markets in three groups: **Agriculture** (Corn, Wheat, Coffee), **Energy** (WTI crude, Natural gas, Brent crude), **Metals** (Gold, Copper, Silver).
Python standard library only (no installs); a local server with a SQLite database; a single-page web app.

```bash
python3 commodity_sim/app.py          # then open http://127.0.0.1:8010/
python3 commodity_sim/app.py --port 0 --db /tmp/x.db     # free port, other database file
```

Saved scenarios and backtests live in `commodity_sim/data/commodity_desk.db` (ignored by git).

## What you can do

| Tab | What it does |
| --- | --- |
| **Market** | Pick a commodity and a seed, then step through the market day by day (or play it). Candlesticks with 20/50/200-day averages, Bollinger bands, RSI, MACD, news events, and Buy/Sell markers. The Signal card gives Buy / Sell / Hold, a −100 to +100 score, confidence, four votes each with a plain-English reason, support/resistance, a stop and target idea, "what would change my mind", and a risk-based size idea |
| **Trade** | A paper account ($100,000): market, stop and limit orders, long and short, up to 3× equity. Orders fill at the **next** day's open. Costs: $2 per fill, 1 bp fee, 5 bp slippage. Equity curve, trade log, working orders, save and reload a scenario |
| **Backtest** | Run the Desk signal, moving-average crossover, RSI reversion, channel breakout or buy-and-hold over the whole window, with your costs and sizing. Metrics next to buy-and-hold, equity and drawdown charts, trade list. **Test on other markets** runs the same rules on up to 300 fresh simulated markets and shows the spread of outcomes. **Sweep** ranks moving-average settings on the first half and scores them on the second half to show overfitting |
| **Learn** | Plain explanations of the indicators, how signals and fills work, how to read a backtest, and what this cannot tell you |

## How it works

- `csim/simulator.py`: seeded price generator. Long-run level pulled back toward (strong for energy), seasonal swing (agriculture, natural gas), momentum (metals), clustered volatility (GARCH-style calm and stormy spells), and labelled news shocks. Same seed, same market. 300 days of history come before day 0.
- `csim/indicators.py`: SMA, EMA, RSI, MACD, Bollinger, ATR, rate of change, realised volatility, z-score, drawdown, seasonal tendency. All **causal**: tests prove an indicator at day t does not change when later days are removed.
- `csim/analysis.py`: four weighted votes (trend, momentum, mean reversion, seasonality) summed to a score. Weights depend on the group: metals lean on trend and momentum, energy on mean reversion, agriculture on mean reversion and seasonality. Volatility lowers confidence.
- `csim/account.py`: one order and fill engine used by hand trading and by the backtester, so both behave the same way.
- `csim/backtest.py`: strategies, metrics (return, per-year, volatility, Sharpe, max drawdown, win rate, profit factor, exposure), many-markets test, parameter sweep.
- `csim/server.py`, `csim/db.py`: loopback-only JSON API and SQLite storage. Requests are checked against DNS-rebinding and cross-site calls (Host and Origin), bodies must be JSON and are size-limited, and errors never leak internals.

## What this is not (please read)

The prices are made up. The simulator **contains the very patterns the signals look for** (energy snaps back, metals trend, agriculture has seasons), so the signals can look sensible here. That only shows the code finds patterns that were put there. Real markets change, patterns fade once many people trade them, and real trading has risks (gaps, liquidity, margin calls, fees, taxes) this model leaves out. Run "Test on other markets": with the same rules, outcomes spread from clearly negative to clearly positive, and the average edge over buy-and-hold is small. **Educational use only; nothing here is investment advice.**

## Tests

```bash
python3 -m unittest discover -s commodity_sim/tests -t commodity_sim        # simulator, indicators, signals, account, backtests, server, database
NODE_PATH=<playwright modules> PW_CHROMIUM=<chromium path> node commodity_sim/tests/ui_smoke.js   # real server + browser end-to-end, incl. 320px layout
```
Highlights: seeded determinism and statistical sanity per group; indicators against hand-computed values (including a textbook RSI example); no look-ahead for indicators, signals and every strategy; account accounting (cash plus position equals equity every bar), gap-through-stop fills, leverage rejection; buy-and-hold equals the price ratio when costs are zero.

## Resume wording (accurate)

"Built a commodity trading simulator (Python standard library, SQLite, vanilla JS): seeded regime-switching price model for nine commodities across agriculture, energy and metals; technical-indicator and signal engine; a paper-trading engine with stop/limit orders and costs; and a backtester with a many-markets test and an overfitting check. Includes a JSON API with request-forgery protections, 70+ unit tests (including no-look-ahead checks) and a browser end-to-end suite." It is a teaching tool on simulated data, not a trading system.
