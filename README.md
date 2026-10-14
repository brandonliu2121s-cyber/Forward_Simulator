# USD/SGD Forwards Market-Making Simulator

A forwards market-making desk simulation, available as two independent versions with identical logic:

| Version | Folder | Use it if you want |
|---|---|---|
| Excel workbook | [`excel/`](excel/) | point-and-click inputs, charts, no install |
| Python CLI | [`python/`](python/) | scripting, batch runs, CSV export |
| Build/verify tools | [`dev/`](dev/) | regenerating the workbook and cross-checking it against the Python model |

- **Pricing** – 45-day USD/SGD forward from covered interest parity (USD 4.00%, SGD 0.55%).
- **Quoting** – USD 250k per side, 5-tick spread, dynamic skew driven by position / limit utilisation.
- **Risk** – automated back-to-back hedges with the street when the position limit or loss limit is breached.

## Model logic

```
Fair forward  F = S × (1 + r_SGD × d/365) / (1 + r_USD × d/360)
Skew (ticks)  = −clamp(position / position_limit, −1, 1) × max_skew
Bid           = round(F/tick + skew − spread/2) × tick;   Ask = Bid + spread × tick
Position limit breach  → hedge to the hedge-to level, pay street half-spread
Loss limit breach      → flatten the book, optionally halt quoting
P&L (SGD)     = spread capture vs fair + MTM of opening position + hedge cost
```

Position convention: net USD bought from clients (+ = long USD). Client BUY lifts our Ask; client SELL hits our Bid.

## Developer notes

```bash
python dev/build_simulator.py            # regenerates excel/*.xlsx (formulas, no cached values)
# recalculate in Excel/LibreOffice and save, then:
python dev/verify_workbook.py            # expect "0 mismatches"
```

## Simplifications

Constant 45-day tenor each step (no roll-down), undiscounted P&L, one RFQ per step at fixed size, instant hedge fills at fair ± street half-spread, illustrative spot level, randomly generated demo scenario (seed 277).
