# Python version

Needs Python 3.8+ and nothing else (standard library only).

```
python simulate_cli.py                               # demo scenario (seed 277): step table + summary
python simulate_cli.py --seed 5 --steps 100 --quiet  # another random scenario, summary only
python simulate_cli.py --spread-ticks 8 --pos-limit 500000 --csv out.csv
python simulate_cli.py --scenario sample_scenario.csv
python simulate_cli.py --help                        # every input as a flag
```

(On Windows use `py` if `python` isn't found.)

- Inputs mirror the Excel **Inputs** sheet (`--base-ir`, `--clip`, `--max-skew-ticks`, `--loss-limit`, ...).
- A scenario file is a CSV with columns `shock` (spot move in ticks) and `action` (BUY/SELL/NONE); see `sample_scenario.csv`.
- `reference_model.py` holds the model itself and can be imported: `from reference_model import DEFAULTS, simulate`.
