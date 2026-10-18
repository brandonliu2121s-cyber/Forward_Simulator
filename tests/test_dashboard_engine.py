"""Cross-check the dashboard's JavaScript engine against reference_model.py for every instrument (needs Node)."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from instruments import ALL, params
from reference_model import generate_scenario, simulate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEYS = ["spot", "fwd", "pos_open", "skew", "bid", "ask", "fill", "edge", "mtm", "pos_breach", "loss_breach",
        "hedge", "hedge_cost", "pos_close", "step_pnl", "cum", "halted"]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class DashboardEngine(unittest.TestCase):
    def test_matches_reference_for_all_instruments(self):
        zs, acts = generate_scenario(277, 60)
        data = dict(instruments=[dict(name=i["name"], params=params(i["name"])) for i in ALL],
                    globals={k: v for k, v in params(ALL[0]["name"]).items() if k in ("hedge_target_pct", "halt_on_loss", "start_pos")},
                    scenario=dict(zs=zs, actions=acts))
        for inst in data["instruments"]:                       # per-instrument params only (globals passed separately)
            for k in ("hedge_target_pct", "halt_on_loss", "start_pos"):
                inst["params"].pop(k, None)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "data.json")
            with open(path, "w") as fh:
                json.dump(data, fh)
            out = subprocess.run(["node", os.path.join(ROOT, "tests", "run_engine.js"), path],
                                 capture_output=True, text=True, check=True).stdout
        js = json.loads(out)
        for inst in ALL:
            ref = simulate(zs, acts, params(inst["name"]))
            rows = js[inst["name"]]
            self.assertEqual(len(rows), len(ref))
            for i, (r, e) in enumerate(zip(rows, ref)):
                for k in KEYS:
                    a = r[{"pos_close": "pos_close"}.get(k, k)]
                    tol = 1e-6 * max(1.0, abs(e[k]))
                    self.assertAlmostEqual(a, e[k], delta=tol, msg=f"{inst['name']} step {i + 1} {k}")


if __name__ == "__main__":
    unittest.main()
