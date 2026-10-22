# Forwards Market-Making Simulator (FX + Commodities)

A forwards market-making desk simulation for **7 FX pairs and 6 commodities** (USD/SGD, EUR/USD, GBP/USD, USD/JPY, AUD/USD,
USD/CHF, USD/CNH, Gold, Silver, WTI Crude, Brent Crude, Copper, Natural Gas) plus an editable custom instrument.
It is available as three front ends that share one model and one instrument library:

| Version | Folder | Use it if you want |
|---|---|---|
| Web dashboard | [`dashboard/`](dashboard/) | a visual desk: charts, gauges, an editable activity log, CSV/JSON import and export. Open one HTML file, no install |
| Excel workbook | [`excel/`](excel/) | point-and-click inputs, charts, live formulas, no install |
| Python CLI | [`python/`](python/) | scripting, batch runs, CSV export, optional live-spot refresh |
| Build, verify and tests | [`dev/`](dev/), [`tests/`](tests/) | regenerating the workbook and dashboard and cross-checking all three against the Python model |

- **Pricing**: fair forward from covered interest parity (FX) or cost of carry (commodities). The original brief is the USD/SGD default: USD 4.00%, SGD 0.55%, 45-day tenor.
- **Quoting**: fixed-size two-way quotes (USD 250k per side, 5-tick spread for USD/SGD) with dynamic skew driven by position / limit utilisation.
- **Risk**: automated back-to-back hedges with the street when the position limit or loss limit is breached.

All spots, rates, sizes and limits other than the USD/SGD brief numbers are **illustrative placeholders, not live market data**.

## Model logic

```
Fair forward  F = S × (1 + rate_B × d/basis_B) / (1 + rate_A × d/basis_A)
   FX BASE/QUOTE : A = base-currency rate,   B = quote-currency rate        (interest-rate parity)
   Commodity     : A = convenience yield,    B = financing + storage cost   (cost of carry)
Spot step     S_t = S_(t-1) + move_σ × step_vol_ticks × tick
Skew (ticks)  = −clamp(position / position_limit, −1, 1) × max_skew
Bid           = round(F/tick + skew − spread/2) × tick;   Ask = Bid + spread × tick
Position-limit breach → hedge back to the residual level, paying the street half-spread
Loss-limit breach     → flatten the book, optionally halt quoting
P&L           = spread capture vs fair + MTM of opening position + hedge cost   (in the quote / P&L currency)
```

Position convention: net units bought from clients (+ = long). Client BUY lifts our Ask; client SELL hits our Bid.
Market moves are in 1-sigma units (scaled by each instrument's step volatility), so one scenario runs on any instrument.

## Developer notes

```bash
python3 dev/build_simulator.py     # regenerates excel/*.xlsx (formulas, no cached values)
python3 dev/build_dashboard.py     # regenerates dashboard/index.html from the template, engine and instrument library
python3 -m unittest discover -s tests -t .     # Python model, live-data parsers, CLI, JS engine == Python (all 14 instruments), import/export suite
# workbook vs. Python model: recalculate with LibreOffice (e.g. the xlsx skill's recalc.py), then
python3 dev/verify_workbook.py --all <recalc.py>        # switches the workbook to every instrument; expect "TOTAL PROBLEMS: 0"
```

`python/instruments.py` is the single source of truth for the instrument library: the workbook, the dashboard and the CLI are all generated from it.
Details for each version are in its own folder's README.
Optional local backend (saved runs and a live-price history in SQLite, `python3 server/app.py`): see `server/README.md`.

## Simplifications

Constant tenor each step (no roll-down), undiscounted P&L, one RFQ per step at fixed size, instant hedge fills at fair ± street half-spread, illustrative levels, randomly generated demo scenario (seed 277).

A separate project, **Commodity Desk** (simulated agriculture, energy and metals markets with analysis, Buy/Sell/Hold signals, paper trading and a backtester), lives in `commodity_sim/`: see `commodity_sim/README.md`.
