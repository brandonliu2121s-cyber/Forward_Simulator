# Web dashboard (Forward Desk)

Open `index.html` in a browser. It is one self-contained file (HTML, CSS and JavaScript): no frontend framework, no backend, no install.

- **Desk**: P&L, spread capture, inventory MTM and hedge cost; an orange hero chart (hover for step detail, click or use the arrow keys to pin a step; markers show limit hedges); a watchlist of all 14 instruments with simulated P&L sparklines; limit-usage bars; a risk-score gauge; generated insights with clickable limit-event chips.
- **Pricing**: the fair-forward derivation, a live bid/ask quote for any inventory, and the skew ladder.
- **Instruments**: the library with fair forwards, forward points and simulated P&L; click a row to load it.
- **Activity**: every step. Edit a market move or click an action (BUY / SELL / NONE) and everything recalculates.
- **Settings**: override any instrument input, resize the scenario (10 to 500 steps), load the Excel scenario or generate a random one.
- **Import / Export**: the arrows button in the top bar, or the buttons on Instruments, Activity and Settings.

Scores: **Health** = share of steps quoting live. **Risk score** (0 to 100, higher is safer) = half inventory headroom plus half loss headroom, minus 4 per position-limit hedge and 10 per loss stop-out; the card also shows what inventory skew was worth against the same run with zero skew.

## Import and export (CSV and JSON)

| Export | Formats | Notes |
|---|---|---|
| Run results | CSV, JSON | Every step: quotes, fills, P&L, hedges. The CSV can be re-imported as a scenario. |
| Scenario only | CSV, JSON | `step,move_sigma,action`. Matches columns A:C of the Excel **Simulation** sheet and the Python CLI's scenario files. |
| Full session | JSON | Instrument, overrides, settings, scenario and results; restores everything on import. |
| Instrument library | CSV, JSON | All instruments including ones you imported. |

Import accepts a file (click or drag and drop) or pasted text, detects the kind, and shows a preview with any errors before you apply it.
A library CSV needs `name,type,unit,pnl,spot,rate_a,rate_b,basis_a,basis_b,tenor_days,tick,clip,spread_ticks,max_skew_ticks,pos_limit,loss_limit,hedge_cost_ticks,step_vol_ticks` (plus optional `note`);
rates may be fractions (`0.04`) or percents (`4%`). The Excel **Instruments** sheet saved as CSV imports too. Add your own currencies or commodities this way.

- Everything imported is validated (types, ranges, size under 2 MB, up to 500 steps); nothing is evaluated, and exported CSV text is guarded against spreadsheet formula injection.
- **Downloads** use a normal browser download. If the page is embedded or sandboxed and the browser blocks it, use **Copy to clipboard** and paste into a file.
- Exported numbers are rounded to 12 significant digits; line endings are CRLF as is standard for CSV.

## Source and tests

`engine.js` (the simulation, a port of `python/reference_model.py`), `io.js` (CSV/JSON import and export) and `template.html` (the UI) are inlined into `index.html` by `dev/build_dashboard.py`; the instrument library comes from `python/instruments.py`.

```bash
python3 dev/build_dashboard.py                                   # rebuild index.html
python3 -m unittest discover -s tests -t .                       # JS engine == Python reference for all 14 instruments; 21-case import/export suite
PW_CHROMIUM=<chromium path> NODE_PATH=<playwright modules> node tests/ui_smoke.js   # optional browser smoke test (Playwright)
```
