# Web dashboard (Forward Desk)

Open `index.html` in a browser. It is one self-contained file (HTML, CSS and JavaScript): no frontend framework, no backend, no install.

- **Setup** (the front page): choose the instrument, override any input, resize the scenario (10 to 500 steps), load the Excel scenario or generate a random one, then press **Run simulation**. Until you run, the other tabs show a short prompt instead of charts; after the run the Desk, Pricing, Instruments and Activity views pop in. Come back to Setup any time and press **Update results**. A link ending in `#desk` (or another view) skips Setup.
- **Desk**: P&L, spread capture, inventory MTM and hedge cost; an orange hero chart (hover for step detail, click or use the arrow keys to pin a step; markers show limit hedges); a watchlist of all 14 instruments with simulated P&L sparklines; limit-usage bars; a risk-score gauge; generated insights with clickable limit-event chips.
- **Pricing**: the fair-forward derivation, a live bid/ask quote for any inventory, and the skew ladder.
- **Instruments**: the library with fair forwards, forward points and simulated P&L; click a row to load it.
- **Activity**: every step. Edit a market move or click an action (BUY / SELL / NONE) and everything recalculates.
- **Import / Export**: the arrows button in the top bar, or the buttons on Instruments, Activity and Setup.

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

## Motion and robustness

Motion follows Emil Kowalski's design-engineering guidance ([emilkowalski/skill](https://github.com/emilkowalski/skill)): crisp and fast, because this is a dashboard people read all day. The data itself never animates.

| Before | After | Why |
| --- | --- | --- |
| Buttons and rows had no press state | `scale(.97)` on `:active`, 160ms, `--ease-out` | Feedback that the click registered |
| Popovers and menus appeared instantly | `scale(.96)` + fade in via `@starting-style`, 150ms, only when opened by pointer | Prevents a jarring change; skipped for keyboard use, which repeats all day |
| Dialogs and toasts popped in and vanished | Enter 200ms / exit 150ms (exits faster than entrances); modals stay centred | Spatial consistency; the system responds quickly |
| Selecting a tab swapped the highlight instantly | The chosen pill pushes up into place (6px rise from `scale(.94)`, 220ms, `--ease-out`) on nav and Export/Import tabs; pointer only | State indication; keyboard tab changes stay instant, and the page content itself does not animate |
| First load showed every card at once | 40ms stagger, 8px rise, first load only | Occasional view, so it is eligible; never blocks interaction |
| Hover styles fired on touch taps | Wrapped in `(hover: hover) and (pointer: fine)` | Touch devices fire false hovers |
| Reduced-motion users got the same movement | Transforms removed, fades kept | Fewer and gentler, not zero |

**Chart reveal.** After **Run simulation**, and again whenever any input, instrument or scenario changes, the visuals build up slowly (about 1.5 s in total) so the change is easy to follow: the P&L line and area wipe in left to right, the key numbers count up to their exact values, the limit-usage bars rise one after another, the risk gauge sweeps, watchlist sparklines draw, health ticks light up and the insight lines fade in. On Pricing the derivation rows and skew-ladder bars build in. It plays once per change, not on every tab visit or toggle (peak/end, range, metric), and it uses Web Animations so nothing lingers afterwards. With reduced motion the visuals simply fade in over 250 ms and numbers are exact straight away.

Deliberately **not** animated: the view content swapping when you change tabs (only the tab pill moves), keyboard-initiated actions (Escape, Enter), the P&L chart and every number (data being read), and the skew ladder (functional table).

Worst-case handling (Emil's break-ui checklist): long names clip with a tooltip, imported names over 40 characters are shortened with a warning, huge and tiny numbers scale to fit instead of truncating, emoji and CJK names get clean initials, plurals read "1 fill" / "2 fills", and no view scrolls sideways down to 320px.

## Live prices (optional, local server)

Served by `python3 server/app.py`, the dashboard starts each instrument from the newest stored live quote instead of the built-in illustrative level, and the Pricing page says so ("Live quote, as of ..."). The Setup page has a **Live prices** card with a "Use live spots" switch and a **Refresh now** button; on open it fetches fresh quotes once if none are stored or the newest is over six hours old. Quotes are delayed and unofficial, interest rates are still manual, and a saved run stores your overrides but not the spot, so loading it later starts from whatever spot is current. Without the server the page keeps the illustrative levels and never goes online.

## Saved runs (optional local database)

Run `python3 server/app.py` and open http://127.0.0.1:8000/. The Setup page then has a **Saved runs** card: name a setup and save it, load it later, delete it. Runs are stored in a SQLite file on your machine (`data/forward_desk.db`). Without the server (opened as a file, or the published artifact) nothing changes and the page stays fully static. See [`server/README.md`](../server/README.md).

## Source and tests

`engine.js` (the simulation, a port of `python/reference_model.py`), `io.js` (CSV/JSON import and export) and `template.html` (the UI) are inlined into `index.html` by `dev/build_dashboard.py`; the instrument library comes from `python/instruments.py`.

```bash
python3 dev/build_dashboard.py                                   # rebuild index.html
python3 -m unittest discover -s tests -t .                       # engine parity, import/export, CLI, motion rules, local database, server and client
PW_CHROMIUM=<chromium path> NODE_PATH=<playwright modules> node tests/ui_smoke.js   # optional browser smoke test (Playwright)
PW_CHROMIUM=<chromium path> NODE_PATH=<playwright modules> node tests/break_ui.js   # worst-case data at 320-1280px (add --demo for baseline data)
```
