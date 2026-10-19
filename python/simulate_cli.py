"""Command-line runner for the forwards market-making simulator (FX pairs and commodities).

Examples:
    python simulate_cli.py                               # USD/SGD, demo scenario (seed 277), table + summary
    python simulate_cli.py --list-instruments
    python simulate_cli.py --instrument "Brent Crude" --quiet
    python simulate_cli.py --instrument Gold --seed 5 --steps 100
    python simulate_cli.py --spread-ticks 8 --pos-limit 500000 --csv out.csv
    python simulate_cli.py --scenario sample_scenario.csv      # columns: move_sigma,action (legacy: shock,action in ticks)
"""
import argparse
import csv
import sys
from decimal import Decimal

from instruments import ALL, DEFAULT, GLOBALS, by_name, params
from reference_model import generate_scenario, simulate

# CLI flag -> (parameter key, type, extra aliases). Defaults come from the chosen instrument, so None = "use the default".
PARAM_FLAGS = [
    ("spot_init", float, []), ("rate_a", float, ["--base-ir"]), ("rate_b", float, ["--quote-ir"]),
    ("basis_a", float, []), ("basis_b", float, []), ("tenor_days", int, []), ("tick", float, []), ("clip", int, []),
    ("spread_ticks", float, []), ("max_skew_ticks", float, []), ("pos_limit", int, []), ("loss_limit", float, []),
    ("hedge_cost_ticks", float, []), ("step_vol_ticks", float, []), ("hedge_target_pct", float, []),
    ("halt_on_loss", int, []), ("start_pos", int, []),
]

# step-table CSV columns: same names as the web dashboard's "Run results" export
CSV_COLUMNS = [("step", "step"), ("move_sigma", "z"), ("action", "act"), ("spot", "spot"), ("fair_forward", "fwd"),
               ("open_position", "pos_open"), ("skew_ticks", "skew"), ("bid", "bid"), ("ask", "ask"), ("fill_units", "fill"),
               ("spread_capture", "edge"), ("mtm", "mtm"), ("hedge_trigger", "trigger"), ("hedge_units", "hedge"),
               ("hedge_cost", "hedge_cost"), ("close_position", "pos_close"), ("step_pnl", "step_pnl"), ("cum_pnl", "cum")]


def find_instrument(text):
    key = text.strip().lower()
    exact = [i for i in ALL if i["name"].lower() == key]
    part = [i for i in ALL if key in i["name"].lower()]
    hit = exact or (part if len(part) == 1 else [])
    if not hit:
        sys.exit(f"Unknown or ambiguous instrument {text!r}. Use --list-instruments to see the options.")
    return hit[0]


def load_scenario(path, step_vol_ticks):
    """CSV with `action` and either `move_sigma` (market move in 1-sigma units) or legacy `shock` (spot move in ticks)."""
    zs, acts = [], []
    with open(path, newline="") as f:
        rd = csv.DictReader(f)
        cols = {(c or "").strip().lower(): c for c in (rd.fieldnames or [])}
        zc = next((cols[k] for k in ("move_sigma", "move", "sigma", "z") if k in cols), None)
        sc = cols.get("shock")
        if "action" not in cols or (zc is None and sc is None):
            sys.exit(f"{path}: needs an 'action' column and a 'move_sigma' (or legacy 'shock', in ticks) column")
        for n, row in enumerate(rd, start=2):
            try:
                z = float(row[zc]) if zc else float(row[sc]) / step_vol_ticks
            except (TypeError, ValueError, ZeroDivisionError):
                sys.exit(f"{path}, line {n}: market move is not a number")
            act = (row[cols["action"]] or "").strip().upper() or "NONE"
            if act not in ("BUY", "SELL", "NONE"):
                sys.exit(f"{path}, line {n}: invalid action {act!r} (use BUY/SELL/NONE)")
            zs.append(z)
            acts.append(act)
    if not zs:
        sys.exit(f"{path}: no steps found")
    return zs, acts


def decimals(tick):
    """Decimals in a tick size. repr(1e-08) is '1e-08', so go through Decimal rather than splitting the string."""
    return max(0, -Decimal(repr(float(tick))).normalize().as_tuple().exponent)


def main():
    ap = argparse.ArgumentParser(description="Forwards market-making simulator (FX pairs and commodities)")
    ap.add_argument("--instrument", default=DEFAULT, help=f"instrument name (default {DEFAULT}); see --list-instruments")
    ap.add_argument("--list-instruments", action="store_true", help="list the built-in instruments and exit")
    ap.add_argument("--seed", type=int, default=277, help="random scenario seed (default 277, the Excel scenario)")
    ap.add_argument("--steps", type=int, default=60, help="number of steps (default 60)")
    ap.add_argument("--scenario", help="CSV with columns move_sigma,action (overrides --seed/--steps)")
    ap.add_argument("--save-scenario", help="write the scenario used to this CSV (step,move_sigma,action)")
    ap.add_argument("--csv", help="write the full step table to this CSV file")
    ap.add_argument("--quiet", action="store_true", help="print only the summary")
    ap.add_argument("--hedge-target", type=float, help="legacy: residual position after a limit hedge, in units (use --hedge-target-pct)")
    for key, typ, aliases in PARAM_FLAGS:
        ap.add_argument("--" + key.replace("_", "-"), *aliases, dest=key, type=typ, default=None,
                        help="override the instrument default")
    args = ap.parse_args()

    if args.list_instruments:
        print(f"{'instrument':<18}{'type':<11}{'unit':<7}{'P&L':<5}{'spot':>12}{'tenor':>7}{'clip':>10}{'spread':>8}{'pos limit':>11}")
        for i in ALL:
            p = params(i["name"])
            print(f"{i['name']:<18}{i['type']:<11}{i['unit']:<7}{i['pnl']:<5}{p['spot_init']:>12,.4f}{p['tenor_days']:>6}d{p['clip']:>10,}{p['spread_ticks']:>8g}{p['pos_limit']:>11,}")
        return

    inst = find_instrument(args.instrument)
    p = params(inst["name"])
    for key, _, _ in PARAM_FLAGS:
        if getattr(args, key) is not None:
            p[key] = getattr(args, key)
    if args.hedge_target is not None:
        p["hedge_target_pct"] = args.hedge_target / p["pos_limit"]
    unit, ccy, dec = inst["unit"], inst["pnl"], decimals(p["tick"])

    if args.scenario:
        zs, acts = load_scenario(args.scenario, p["step_vol_ticks"])
    else:
        zs, acts = generate_scenario(args.seed, args.steps)

    rows = simulate(zs, acts, p)
    for i, r in enumerate(rows):
        r["step"], r["z"], r["act"] = i + 1, zs[i], acts[i]
        r["trigger"] = "LOSS LIMIT" if r["loss_breach"] else "POSITION LIMIT" if r["pos_breach"] else ""

    if args.save_scenario:
        with open(args.save_scenario, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["step", "move_sigma", "action"])
            w.writerows([i + 1, zs[i], acts[i]] for i in range(len(zs)))
        print(f"Wrote scenario ({len(zs)} steps) to {args.save_scenario}")

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([c[0] for c in CSV_COLUMNS] + ["status"])
            for r in rows:
                w.writerow([r[c[1]] for c in CSV_COLUMNS] + ["HALTED" if r["halted"] else "LIVE"])
        print(f"Wrote {len(rows)} rows to {args.csv}")

    if not args.quiet:
        w = max(8, dec + 6)
        print(f"{inst['name']} ({inst['type']}), position in {unit}, P&L in {ccy}")
        print(f"{'step':>4} {'act':>4} {'fwd':>{w}} {'bid':>{w}} {'ask':>{w}} {'fill':>10} {'hedge':>10} {'pos':>10} {'step P&L':>11} {'cum P&L':>11}  flags")
        for r in rows:
            flags = ("POS-HEDGE " if r["pos_breach"] and not r["loss_breach"] else "") + \
                    ("LOSS-FLAT " if r["loss_breach"] else "") + ("HALTED" if r["halted"] else "")
            print(f"{r['step']:>4} {r['act']:>4} {r['fwd']:>{w}.{dec + 1}f} {r['bid']:>{w}.{dec}f} {r['ask']:>{w}.{dec}f} "
                  f"{r['fill']:>10,.0f} {r['hedge']:>10,.0f} {r['pos_close']:>10,.0f} "
                  f"{r['step_pnl']:>11,.2f} {r['cum']:>11,.2f}  {flags.strip()}")

    fills = [r for r in rows if r["fill"]]
    loss_steps = [r["step"] for r in rows if r["loss_breach"]]
    print("\nSummary")
    print(f"  Instrument:         {inst['name']}")
    print(f"  Steps:              {len(rows)}")
    print(f"  Client fills:       {len(fills)}")
    print(f"  Position hedges:    {sum(1 for r in rows if r['pos_breach'] and not r['loss_breach'])}")
    print(f"  Loss-limit breach:  {'step ' + str(loss_steps[0]) if loss_steps else 'none'}")
    print(f"  Max |position|:     {max(abs(r['pos_close']) for r in rows):,.0f} {unit}")
    print(f"  Spread capture:     {sum(r['edge'] for r in rows):,.2f} {ccy}")
    print(f"  MTM:                {sum(r['mtm'] for r in rows):,.2f} {ccy}")
    print(f"  Hedge cost:         {sum(r['hedge_cost'] for r in rows):,.2f} {ccy}")
    print(f"  Total P&L:          {rows[-1]['cum']:,.2f} {ccy}")


if __name__ == "__main__":
    main()
