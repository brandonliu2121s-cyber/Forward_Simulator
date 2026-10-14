"""Command-line runner for the forwards market-making simulator.

Examples:
    python simulate_cli.py                          # demo scenario (seed 277), print table + summary
    python simulate_cli.py --seed 5 --steps 100
    python simulate_cli.py --spread-ticks 8 --pos-limit 500000 --csv out.csv
    python simulate_cli.py --scenario my_scenario.csv   # columns: shock,action
"""
import argparse
import csv
import sys

from reference_model import DEFAULTS, generate_scenario, simulate

# CLI flag -> parameter key (all numeric)
PARAM_FLAGS = {
    "spot_init": float, "base_ir": float, "quote_ir": float, "tenor_days": int,
    "clip": int, "spread_ticks": float, "max_skew_ticks": float, "pos_limit": int,
    "hedge_target": int, "hedge_cost_ticks": float, "loss_limit": float,
    "halt_on_loss": int, "start_pos": int,
}

COLUMNS = ["step", "action", "spot", "fwd", "pos_open", "skew", "bid", "ask", "fill",
           "edge", "mtm", "hedge", "hedge_cost", "pos_close", "step_pnl", "cum",
           "pos_breach", "loss_breach", "halted"]


def load_scenario(path):
    shocks, actions = [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            shocks.append(int(row["shock"]))
            action = row["action"].strip().upper()
            if action not in ("BUY", "SELL", "NONE"):
                sys.exit(f"Invalid action {action!r} in {path} (use BUY/SELL/NONE)")
            actions.append(action)
    return shocks, actions


def main():
    ap = argparse.ArgumentParser(description="USD/SGD forwards market-making simulator")
    ap.add_argument("--seed", type=int, default=277, help="random scenario seed (default 277)")
    ap.add_argument("--steps", type=int, default=60, help="number of steps (default 60)")
    ap.add_argument("--shock-sd", type=float, default=3.0, help="spot shock std dev in ticks")
    ap.add_argument("--scenario", help="CSV with columns shock,action (overrides --seed/--steps)")
    ap.add_argument("--csv", help="write the full step table to this CSV file")
    ap.add_argument("--quiet", action="store_true", help="print only the summary")
    for key, typ in PARAM_FLAGS.items():
        ap.add_argument("--" + key.replace("_", "-"), type=typ, default=DEFAULTS[key],
                        help=f"default {DEFAULTS[key]}")
    args = ap.parse_args()

    p = dict(DEFAULTS)
    for key in PARAM_FLAGS:
        p[key] = getattr(args, key)

    if args.scenario:
        shocks, actions = load_scenario(args.scenario)
    else:
        shocks, actions = generate_scenario(args.seed, args.steps, args.shock_sd)

    rows = simulate(shocks, actions, p)
    for i, (r, a) in enumerate(zip(rows, actions), 1):
        r["step"], r["action"] = i, a

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"Wrote {len(rows)} rows to {args.csv}")

    if not args.quiet:
        print(f"{'step':>4} {'act':>4} {'fwd':>8} {'bid':>8} {'ask':>8} {'fill':>9} "
              f"{'hedge':>9} {'pos':>9} {'step P&L':>9} {'cum P&L':>9}  flags")
        for r in rows:
            flags = ("POS-HEDGE " if r["pos_breach"] and not r["loss_breach"] else "") + \
                    ("LOSS-FLAT " if r["loss_breach"] else "") + ("HALTED" if r["halted"] else "")
            print(f"{r['step']:>4} {r['action']:>4} {r['fwd']:>8.4f} {r['bid']:>8.4f} {r['ask']:>8.4f} "
                  f"{r['fill']:>9,} {r['hedge']:>9,} {r['pos_close']:>9,} "
                  f"{r['step_pnl']:>9,.1f} {r['cum']:>9,.1f}  {flags.strip()}")

    fills = [r for r in rows if r["fill"]]
    print("\nSummary")
    print(f"  Steps:              {len(rows)}")
    print(f"  Client fills:       {len(fills)}")
    print(f"  Position hedges:    {sum(1 for r in rows if r['pos_breach'] and not r['loss_breach'])}")
    loss_steps = [r["step"] for r in rows if r["loss_breach"]]
    print(f"  Loss-limit breach:  {'step ' + str(loss_steps[0]) if loss_steps else 'none'}")
    print(f"  Max |position|:     {max(abs(r['pos_close']) for r in rows):,}")
    print(f"  Spread capture:     {sum(r['edge'] for r in rows):,.1f} SGD")
    print(f"  MTM:                {sum(r['mtm'] for r in rows):,.1f} SGD")
    print(f"  Hedge cost:         {sum(r['hedge_cost'] for r in rows):,.1f} SGD")
    print(f"  Total P&L:          {rows[-1]['cum']:,.1f} SGD")


if __name__ == "__main__":
    main()
