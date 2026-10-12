# Forwards Market-Making Simulator (FX + Commodities)

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
| `verify_workbook.py` | Cross-checks every simulated cell against the reference model, for one instrument or all of them. |

## Using it

1. **Inputs**: choose the instrument in `C4`. Each assumption shows the instrument default, an optional *Override* (blue on yellow) and the *ACTIVE* value the model uses.
2. **Instruments**: the library, with a live fair forward / forward points / premium-discount for every instrument. Edit any row or overwrite the Custom row to add your own.
3. **Simulation**: edit the blue columns: *market move* (in sigma units, so one scenario runs on every instrument) and *client action* (BUY/SELL/NONE).
4. **Summary** shows activity, P&L attribution, limit usage, integrity checks and charts. **Pricing** has a quote calculator and skew ladder for any inventory.

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
```

## Simplifications

Constant tenor each step (no roll-down), undiscounted P&L, one RFQ per step at fixed size, instant hedge fills at fair ± street half-spread, illustrative spot levels / rates / sizes / limits, randomly generated demo scenario (seed 277).
