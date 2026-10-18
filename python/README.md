# Python version

Needs Python 3.8+ and nothing else (standard library only). Run these from this folder.

```
python simulate_cli.py                               # USD/SGD, demo scenario (seed 277): step table + summary
python simulate_cli.py --list-instruments
python simulate_cli.py --instrument "Brent Crude" --quiet
python simulate_cli.py --instrument Gold --seed 5 --steps 100 --quiet
python simulate_cli.py --spread-ticks 8 --pos-limit 500000 --csv out.csv
python simulate_cli.py --scenario sample_scenario.csv
python simulate_cli.py --help                        # every input as a flag
```

(On Windows use `py` if `python` isn't found.)

- `--instrument` takes a name or a unique part of one (`brent`, `gold`, `usd/jpy`). Every instrument input can be overridden by a flag (`--spread-ticks`, `--clip`, `--loss-limit`, `--rate-a`, `--rate-b`, ...); the old `--base-ir` / `--quote-ir` / `--hedge-target` flags still work.
- A scenario file is a CSV with `action` (BUY/SELL/NONE) and `move_sigma` (market move in 1-sigma units; the same format the web dashboard and the Excel Simulation sheet use). The older `shock,action` format (spot move in ticks), as in `sample_scenario.csv`, still works.
- `--csv out.csv` writes the full step table with the same columns as the dashboard's "Run results" export; `--save-scenario sc.csv` saves the scenario used.
- `instruments.py` holds the instrument library and `reference_model.py` the model itself; both can be imported: `from reference_model import simulate`, `from instruments import params`.
- The old `--shock-sd` flag is gone: moves are now in sigma units scaled by each instrument's step volatility.

## Optional: live spot prices

`refresh_live.py` fetches spot prices into `live_snapshot.json` (repo root) and rebuilds the Excel workbook; no server or frontend is needed.

```
python refresh_live.py                          # Yahoo (FX + commodity futures) -> live_snapshot.json -> rebuild the workbook
python refresh_live.py --provider frankfurter   # FX only, ECB daily fixing (not intraday)
```

Then open the workbook, go to **Inputs** and set *Use live spot* = 1. The **Live** sheet shows each instrument's live spot, timestamp, source and the fair forward at the live spot.

- **Only spot is live.** Interest rates, convenience yields, sizes and limits stay manual on the Instruments sheet.
- It is a **snapshot, not a stream.** Free sources are delayed (Yahoo about 15 minutes; Frankfurter once a day).
- Commodity prices are **front-month futures** (copper is converted from USD/lb to USD/tonne), not physical spot.
- The Yahoo endpoint is unofficial and can change or rate-limit without notice. A quote that fails falls back to the library spot, and a failed refresh never overwrites a good snapshot.
- **Tested against the real Yahoo endpoint** from the build environment on 2026-10-18: all 14 quotes came back and parsed. The Frankfurter provider could not be reached from that environment, so it is covered by canned-payload unit tests only.
- Some levels differ a lot from the library's placeholder spots (for example crude oil), which is a good reason to use live mode.
- Educational use only: delayed, unofficial data must not drive trading decisions.
