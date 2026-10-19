"""Run the Node tests for dashboard/store.js (client of the local server) against an in-memory fake fetch."""
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class StoreSuite(unittest.TestCase):
    def test_store_suite(self):
        res = subprocess.run(["node", os.path.join(ROOT, "tests", "test_store.js")], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


if __name__ == "__main__":
    unittest.main()
