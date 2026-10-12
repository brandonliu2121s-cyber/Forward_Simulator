# USD/SGD Forwards Market-Making Simulator

An Excel simulation of a forwards market-making desk:

- **Pricing** – 45-day USD/SGD forward from covered interest parity (USD 4.00%, SGD 0.55%).
- **Quoting** – USD 250k per side, 5-tick spread, with dynamic skew driven by live position / limit utilisation.
- **Risk** – automated back-to-back hedges with the street when the position limit or loss limit is breached.

## Files

| File | Purpose |
|---|---|
| `Forwards_Market_Making_Simulator.xlsx` | The workbook (Guide, Inputs, Pricing, Simulation, Summary). All logic is live Excel formulas. |
| `build_simulator.py` | Regenerates the workbook. |
| `reference_model.py` | Independent pure-Python implementation of the same logic (also generates the demo scenario). |
| `verify_workbook.py` | Cross-checks every simulated cell in the recalculated workbook against the reference model. |

## Using it

1. Change assumptions on **Inputs** (blue on yellow cells): rates, tenor, clip size, spread, skew, limits, hedge cost.
2. On **Simulation**, edit the blue columns – *spot shock (ticks)* and *client action (BUY/SELL/NONE)* – to run your own scenario.
3. Read the results on **Summary** (activity, P&L attribution, limit usage, charts). **Pricing** has a quote calculator for any inventory and a skew ladder.

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

## Rebuilding

```bash
python3 build_simulator.py                              # writes the .xlsx (formulas, no cached values)
python3 <xlsx-skill>/scripts/recalc.py Forwards_Market_Making_Simulator.xlsx   # LibreOffice recalculation
python3 verify_workbook.py                              # expect "0 mismatches"
```

## Simplifications

Constant 45-day tenor each step (no roll-down), undiscounted P&L, one RFQ per step at fixed size, instant hedge fills at fair ± street half-spread, illustrative spot level, randomly generated demo scenario (seed 277).
