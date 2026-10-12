"""Cross-check the workbook against the pure-Python reference model.

    python3 verify_workbook.py                       # check the instrument currently selected in the file
    python3 verify_workbook.py --all <recalc.py>     # switch to EVERY instrument, recalculate with LibreOffice, compare

<recalc.py> is the xlsx skill's recalculation script (LibreOffice headless).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from openpyxl import load_workbook

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python"))
from instruments import ALL, params
from reference_model import fair_forward, simulate

PATH = os.path.join(HERE, "..", "excel", "Forwards_Market_Making_Simulator.xlsx")
COLS = dict(spot="D", fwd="E", pos_open="G", skew="I", bid="J", ask="K", fill="M", edge="P", mtm="Q",
            pos_breach="S", loss_breach="T", hedge="V", hedge_cost="X", pos_close="Y",
            step_pnl="Z", cum="AA", halted="AB")


def check(path, instrument):
    wb = load_workbook(path, data_only=True)
    ws = wb["Simulation"]
    assert wb["Inputs"]["C4"].value == instrument, "selector mismatch"
    p = params(instrument)
    zs = [ws.cell(row=r, column=2).value for r in range(7, 67)]
    acts = [ws.cell(row=r, column=3).value for r in range(7, 67)]
    ref = simulate(zs, acts, p)
    bad = 0
    for i, row in enumerate(ref):
        for key, col in COLS.items():
            x = ws[f"{col}{7 + i}"].value
            tol = 1e-6 * max(1.0, abs(row[key]))
            if abs((x or 0) - row[key]) > tol:
                bad += 1
                if bad <= 5:
                    print(f"  MISMATCH {instrument} step {i + 1} {key}: excel={x} ref={row[key]}")
    # fair forward in the Instruments library table
    names = [c.value for c in wb["Instruments"]["B"][5:5 + len(ALL)]]
    row = 6 + names.index(instrument)
    fx = wb["Instruments"][f"V{row}"].value
    if abs(fx - fair_forward(p["spot_init"], p)) > 1e-9 * p["spot_init"]:
        bad += 1
        print(f"  MISMATCH {instrument} Instruments fair forward: excel={fx}")
    # Summary integrity checks
    su = wb["Summary"]
    checks = [su.cell(row=r, column=3).value for r in range(1, 60) if su.cell(row=r, column=3).value in ("OK", "ERROR")]
    if checks != ["OK"] * 3:
        bad += 1
        print(f"  INTEGRITY CHECKS {instrument}: {checks}")
    print(f"{instrument:18s} {len(ref) * len(COLS)} cells checked, {bad} problems")
    return bad


if __name__ == "__main__":
    if "--all" in sys.argv:
        recalc = sys.argv[sys.argv.index("--all") + 1]
        total = 0
        with tempfile.TemporaryDirectory() as tmp:
            for inst in ALL:
                f = Path(tmp) / "wb.xlsx"
                wb = load_workbook(PATH)
                wb["Inputs"]["C4"] = inst["name"]
                wb.save(f)
                out = subprocess.run([sys.executable, recalc, str(f), "120"], capture_output=True, text=True).stdout
                res = json.loads(out)
                if res.get("status") != "success":
                    print(inst["name"], "RECALC ERRORS:", res)
                    total += 1
                    continue
                total += check(f, inst["name"])
        print("TOTAL PROBLEMS:", total)
        sys.exit(1 if total else 0)
    wb = load_workbook(PATH, data_only=True)
    sys.exit(1 if check(PATH, wb["Inputs"]["C4"].value) else 0)
