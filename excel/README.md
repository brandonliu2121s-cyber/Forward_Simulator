# Excel version

Open `Forwards_Market_Making_Simulator.xlsx` (Excel 2016+ or LibreOffice). No macros, no add-ins; all logic is live formulas.

1. **Guide**: overview of the sheets.
2. **Inputs**: choose the instrument in `C4` (7 FX pairs, 6 commodities, one custom row). Each assumption shows the instrument default, an optional *Override* (blue on yellow) and the *ACTIVE* value the model uses.
3. **Instruments**: the library, with a live fair forward / forward points / premium-discount for every instrument. Edit any row or overwrite the Custom row to add your own.
4. **Live**: optional live-spot snapshot (see [`../python/README.md`](../python/README.md)); set *Use live spot* = 1 on Inputs to use it. Default is 0.
5. **Simulation**: edit the blue columns *market move (sigma units)* and *client action (BUY/SELL/NONE)* to run your own scenario.
6. **Summary**: activity, P&L attribution, limit usage, integrity checks and charts. **Pricing** has a quote calculator and skew ladder.

The scenario CSV exported by the web dashboard (`step,move_sigma,action`) pastes straight into columns A:C of the Simulation sheet, and the Instruments sheet saved as CSV imports into the dashboard.
