"""Tests for python/simulate_cli.py (run as a subprocess, as a user would)."""
import csv
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))
from instruments import ALL, params  # noqa: E402
from reference_model import generate_scenario, simulate  # noqa: E402

CLI = os.path.join(ROOT, "python", "simulate_cli.py")


def run(*args, ok=True):
    res = subprocess.run([sys.executable, CLI, *args], capture_output=True, text=True, cwd=os.path.join(ROOT, "python"))
    if ok:
        assert res.returncode == 0, res.stderr
    return res


def total_pnl(out):
    line = next(l for l in out.splitlines() if l.strip().startswith("Total P&L"))
    return float(line.split(":")[1].split()[0].replace(",", ""))


class SimulateCLI(unittest.TestCase):
    def test_default_matches_reference_model_for_every_instrument(self):
        zs, acts = generate_scenario(277, 60)
        for inst in ALL:
            want = simulate(zs, acts, params(inst["name"]))[-1]["cum"]
            got = total_pnl(run("--instrument", inst["name"], "--quiet").stdout)
            self.assertAlmostEqual(got, want, places=2, msg=inst["name"])

    def test_list_instruments_includes_brent(self):
        out = run("--list-instruments").stdout
        self.assertIn("Brent Crude", out)
        self.assertEqual(sum(1 for l in out.splitlines()[1:] if l.strip()), len(ALL))

    def test_instrument_prefix_and_ambiguity(self):
        self.assertIn("Brent Crude", run("--instrument", "brent", "--quiet").stdout)
        res = run("--instrument", "crude", ok=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("ambiguous", res.stderr)

    def test_overrides_and_legacy_aliases(self):
        base = total_pnl(run("--quiet").stdout)
        self.assertNotEqual(total_pnl(run("--spread-ticks", "12", "--quiet").stdout), base)
        self.assertAlmostEqual(total_pnl(run("--base-ir", "0.04", "--quote-ir", "0.0055", "--quiet").stdout), base, places=2)

    def test_scenario_round_trip_and_csv_export(self):
        with tempfile.TemporaryDirectory() as d:
            sc, out = os.path.join(d, "sc.csv"), os.path.join(d, "run.csv")
            first = total_pnl(run("--seed", "5", "--steps", "40", "--save-scenario", sc, "--csv", out, "--quiet").stdout)
            again = total_pnl(run("--scenario", sc, "--quiet").stdout)
            self.assertAlmostEqual(first, again, places=2)
            rows = list(csv.DictReader(open(out)))
            self.assertEqual(len(rows), 40)
            self.assertEqual(list(rows[0])[:3], ["step", "move_sigma", "action"])   # same columns as the dashboard export
            self.assertEqual(list(csv.DictReader(open(sc)))[0].keys(), {"step", "move_sigma", "action"})

    def test_legacy_shock_scenario_file_still_works(self):
        res = run("--scenario", os.path.join(ROOT, "python", "sample_scenario.csv"), "--quiet")
        self.assertIn("Summary", res.stdout)

    def test_bad_scenario_rows_are_reported(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.csv")
            open(p, "w").write("move_sigma,action\n1,BUY\nx,SELL\n")
            res = run("--scenario", p, ok=False)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("line 3", res.stderr)


if __name__ == "__main__":
    unittest.main()
