# Forwards Market-Making Simulator (FX + Commodities)

Two front ends over the same model: an **Excel workbook** and a **web dashboard** (`dashboard/index.html`, no server needed).

An Excel simulation of a forwards market-making desk. Pick any instrument from a dropdown and the whole
workbook re-prices:

- **Pricing**: fair forward from covered interest parity (FX) or cost of carry (commodities).
- **Quoting**: fixed-size two-way quotes with a bid/offer spread and dynamic skew driven by live position / limit utilisation.
- **Risk**: automated back-to-back hedges with the street when the position limit or loss limit is breached.

Built-in instruments (all inputs are **illustrative placeholders, not live market data**):

| Type | Instruments |
|---|---|
| FX (7) | USD/SGD (the original brief: USD 4.00%, SGD 0.55%, 45d, USD 250k, 5 ticks), EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CHF, USD/CNH |
| Commodity (5) | Gold, Silver, WTI Crude, Copper, Natural Gas |
| Custom (1) | An editable example row (USD/MYR): overwrite it with any currency pair or commodity |

## Files

| File | Purpose |
|---|---|
| `Forwards_Market_Making_Simulator.xlsx` | The workbook (Guide, Inputs, Instruments, Pricing, Simulation, Summary). All logic is live Excel formulas. |
| `instruments.py` | Instrument library (single source of truth for the workbook and the checks). |
| `build_simulator.py` | Regenerates the workbook. |
| `reference_model.py` | Independent pure-Python implementation of the same logic (also generates the demo scenario). |
| `dashboard/index.html` | The **Forward Desk** web dashboard (single self-contained file: open it in any browser). Built by `build_dashboard.py`. |
| `dashboard/engine.js`, `dashboard/template.html` | Dashboard source: the simulation engine (a port of `reference_model.py`) and the UI. |
| `build_dashboard.py` | Regenerates `dashboard/index.html` from the template, the engine and `instruments.py`. |
| `verify_workbook.py` | Cross-checks every simulated cell against the reference model, for one instrument or all of them (optionally in live-spot mode). |
| `live_data.py`, `refresh_live.py` | Optional live-spot snapshot: fetch prices, write `live_snapshot.json`, rebuild the workbook. Stdlib only. |
| `tests/` | Unit tests for the live-data parsers (canned payloads, no network) and a synthetic snapshot fixture. |

## Dashboard (Forward Desk)

Open `dashboard/index.html` in a browser. Pure HTML, CSS and JavaScript: no frontend framework, no backend, no install.

- **Desk**: P&L, spread capture, inventory MTM and hedge cost; an orange hero chart (hover for step detail, click or use the arrow keys to pin a step; markers show limit hedges); a watchlist of all 13 instruments with simulated P&L sparklines; limit-usage bars; a risk-score gauge; generated insights with clickable limit-event chips.
- **Pricing**: the fair-forward derivation, a live bid/ask quote for any inventory, and the skew ladder.
- **Instruments**: the library with fair forwards, forward points and simulated P&L; click a row to load it.
- **Activity**: every step. Edit a market move or click an action (BUY / SELL / NONE) and everything recalculates.
- **Settings**: override any instrument input, resize the scenario, load the Excel scenario or generate a random one.

Scores: **Health** = share of steps quoting live. **Risk score** (0 to 100, higher is safer) = half inventory headroom plus half loss headroom, minus 4 per position-limit hedge and 10 per loss stop-out; the card also shows what inventory skew was worth against the same run with zero skew.

```bash
python3 build_dashboard.py                                     # rebuild dashboard/index.html
python3 -m unittest discover -s tests -t .                     # includes: JS engine == Python reference, all 13 instruments
PW_CHROMIUM=<chromium path> NODE_PATH=<playwright modules> node tests/ui_smoke.js   # optional UI smoke test (Playwright)
```

## Using the Excel workbook

1. **Inputs**: choose the instrument in `C4`. Each assumption shows the instrument default, an optional *Override* (blue on yellow) and the *ACTIVE* value the model uses.
2. **Instruments**: the library, with a live fair forward / forward points / premium-discount for every instrument. Edit any row or overwrite the Custom row to add your own.
3. **Simulation**: edit the blue columns: *market move* (in sigma units, so one scenario runs on every instrument) and *client action* (BUY/SELL/NONE).
4. **Summary** shows activity, P&L attribution, limit usage, integrity checks and charts. **Pricing** has a quote calculator and skew ladder for any inventory.

## Optional: live spot prices

No frontend or server is needed: Excel is the UI and a small Python script is the data refresher.

```bash
python3 refresh_live.py                      # fetch spots -> live_snapshot.json -> rebuild the workbook
python3 refresh_live.py --provider frankfurter   # FX only, ECB daily fixing (not intraday)
```

Then open the workbook, go to **Inputs** and set *Use live spot* = 1. The **Live** sheet shows every instrument's live spot,
timestamp, source and the fair forward at the live spot. The default is 0, so the workbook never depends on a feed.

- **Only spot is live.** Interest rates, convenience yields, sizes and limits stay manual on the Instruments sheet.
- It is a **snapshot, not a stream.** Free sources are delayed (Yahoo ~15 min; Frankfurter once a day).
- Commodity prices are **front-month futures** (copper is converted from USD/lb to USD/tonne), not physical spot.
- The Yahoo endpoint is unofficial and can change or rate-limit without notice. Any quote that fails falls back to the library spot.
- **Not tested against the real feeds yet:** the build environment blocked them, so the parsers are covered by canned-payload unit tests only. Run `refresh_live.py` once on a machine with internet and check the output.
- Educational use only: delayed, unofficial data must not drive trading decisions.

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

## Rebuilding and verifying

```bash
python3 build_simulator.py                                   # writes the .xlsx (formulas, no cached values)
python3 <xlsx-skill>/scripts/recalc.py Forwards_Market_Making_Simulator.xlsx   # LibreOffice recalculation
python3 verify_workbook.py --all <xlsx-skill>/scripts/recalc.py                # switches to all 13 instruments; expect "TOTAL PROBLEMS: 0"
python3 verify_workbook.py --all <xlsx-skill>/scripts/recalc.py --snapshot tests/fixtures/snapshot_fixture.json   # same, in live-spot mode
python3 -m unittest discover -s tests -t .                                     # live-data parser tests
```

## Simplifications

Constant tenor each step (no roll-down), undiscounted P&L, one RFQ per step at fixed size, instant hedge fills at fair ± street half-spread, illustrative spot levels / rates / sizes / limits, randomly generated demo scenario (seed 277).
