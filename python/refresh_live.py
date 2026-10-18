"""Refresh live spot prices and rebuild the workbook.

    python3 python/refresh_live.py                       # yahoo provider, writes live_snapshot.json, rebuilds the .xlsx
    python3 python/refresh_live.py --provider frankfurter
    python3 python/refresh_live.py --no-rebuild          # only write live_snapshot.json
    python3 python/refresh_live.py --recalc <path to recalc.py>   # also recalculate with LibreOffice (optional)

Then open Forwards_Market_Making_Simulator.xlsx, go to Inputs and set 'Use live spot' = 1.
Educational use only: delayed, unofficial data; not for trading decisions.
"""
import argparse
import os
import subprocess
import sys

from live_data import fetch_all, write_snapshot

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT = os.path.join(ROOT, "live_snapshot.json")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", choices=["yahoo", "frankfurter"], default="yahoo")
    ap.add_argument("--snapshot", default=SNAPSHOT)
    ap.add_argument("--no-rebuild", action="store_true")
    ap.add_argument("--recalc", help="path to the xlsx skill's recalc.py (LibreOffice) to compute cached values")
    a = ap.parse_args(argv)

    results = fetch_all(a.provider)
    ok = sum(1 for r in results.values() if r["price"] is not None)
    print(f"{a.provider}: {ok}/{len(results)} quotes fetched")
    for nm, r in results.items():
        print(f"  {nm:18s} {r['price'] if r['price'] is not None else '-':>12}  {r['as_of'] or ''}  {r['status']}")
    if ok == 0:
        # never overwrite a previously good snapshot with an all-error one
        print(f"No quotes fetched: keeping any existing {a.snapshot} and NOT rebuilding. "
              "Check your network / provider.", file=sys.stderr)
        return 1
    doc = write_snapshot(results, a.snapshot)
    print(f"snapshot written at {doc['fetched_utc']} UTC -> {a.snapshot}")
    if ok < len(results):
        print("Some quotes failed: those instruments fall back to their library spot in the workbook.")
    if not a.no_rebuild:
        subprocess.run([sys.executable, os.path.join(ROOT, "dev", "build_simulator.py"), "--snapshot", a.snapshot], check=True)
        if a.recalc:
            subprocess.run([sys.executable, a.recalc, os.path.join(ROOT, "excel", "Forwards_Market_Making_Simulator.xlsx"), "120"], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
