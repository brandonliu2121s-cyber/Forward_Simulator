"""Cross-check the recalculated workbook against the pure-Python reference model."""
import os, sys
from openpyxl import load_workbook
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))
from reference_model import DEFAULTS, simulate

path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "excel", "Forwards_Market_Making_Simulator.xlsx")
ws = load_workbook(path, data_only=True)["Simulation"]
shocks = [ws.cell(row=r, column=2).value for r in range(7, 67)]
actions = [ws.cell(row=r, column=3).value for r in range(7, 67)]
ref = simulate(shocks, actions, DEFAULTS)
cols = dict(spot="D", fwd="E", pos_open="G", skew="I", bid="J", ask="K", fill="M", edge="P", mtm="Q",
            pos_breach="S", loss_breach="T", hedge="V", hedge_cost="X", pos_close="Y",
            step_pnl="Z", cum="AA", halted="AB")
bad = 0
for i, row in enumerate(ref):
    for key, col in cols.items():
        x = ws[f"{col}{7 + i}"].value
        if abs((x or 0) - row[key]) > 1e-6:
            bad += 1
            print(f"MISMATCH step {i + 1} {key}: excel={x} ref={row[key]}")
print("checked", len(ref) * len(cols), "cells;", bad, "mismatches")
sys.exit(1 if bad else 0)
