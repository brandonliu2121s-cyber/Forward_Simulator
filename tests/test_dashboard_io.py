"""Run the Node test-suite for dashboard/io.js (CSV/JSON import and export) against the real instrument library."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))
sys.path.insert(0, os.path.join(ROOT, "dev"))
import build_dashboard  # noqa: E402


@unittest.skipUnless(shutil.which("node"), "node not installed")
class DashboardIO(unittest.TestCase):
    def test_io_suite(self):
        data = json.loads(build_dashboard.data_json().replace("<\\/", "</"))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "data.json")
            with open(path, "w") as fh:
                json.dump(data, fh)
            res = subprocess.run(["node", os.path.join(ROOT, "tests", "test_io.js"), path], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


if __name__ == "__main__":
    unittest.main()
