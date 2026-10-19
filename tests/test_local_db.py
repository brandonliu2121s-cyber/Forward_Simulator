"""SQLite layer (python/local_db.py): saved runs, price snapshots, validation. In-memory and temp-file databases, no network."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))
import local_db as ldb  # noqa: E402

QUOTES = {
    "USD/SGD": dict(price=1.2795, as_of="2026-10-19 14:30:00", source="yahoo:SGD=X", status="ok"),
    "EUR/USD": dict(price=1.1629, as_of="2026-10-19 (ECB daily fixing)", source="frankfurter:EUR/USD", status="ok"),
    "Gold": dict(price=None, as_of=None, source="yahoo:GC=F", status="error: boom"),
    "Odd": dict(price=1.0, as_of="not a date", source="x", status="ok"),
}


class Runs(unittest.TestCase):
    def setUp(self):
        self.db = ldb.Database(":memory:")

    def test_round_trip_newest_first(self):
        a = self.db.add_run("  Base case ", "USD/SGD", {"format": "forward-desk-session", "overrides": {"spread_ticks": 9}}, {"pnl": -1928.13})
        b = self.db.add_run("Wide", "EUR/USD", {"x": 1})
        self.assertEqual(a["name"], "Base case")
        self.assertEqual([r["name"] for r in self.db.list_runs()], ["Wide", "Base case"])
        got = self.db.get_run(a["id"])
        self.assertEqual(got["session"]["overrides"]["spread_ticks"], 9)
        self.assertEqual(got["summary"]["pnl"], -1928.13)
        self.assertNotIn("session", self.db.list_runs()[0])                         # the list stays light
        self.assertTrue(self.db.delete_run(b["id"]))
        self.assertFalse(self.db.delete_run(b["id"]))
        self.assertIsNone(self.db.get_run(b["id"]))
        self.assertEqual(self.db.count_runs(), 1)

    def test_validation(self):
        for args in [("  ", "USD/SGD", {}), ("ok", "", {}), ("ok", "x", [1]), ("ok", "x", "text"), (None, "x", {})]:
            with self.assertRaises(ldb.ValidationError):
                self.db.add_run(*args)
        with self.assertRaises(ldb.ValidationError):
            self.db.add_run("ok", "x", {}, ["not", "an", "object"])
        with self.assertRaises(ldb.ValidationError):
            self.db.add_run("ok", "x", {"blob": "y" * (ldb.MAX_SESSION_BYTES + 1)})
        self.assertEqual(self.db.count_runs(), 0)

    def test_long_names_are_clipped_not_rejected(self):
        r = self.db.add_run("n" * 200, "i" * 200, {})
        self.assertEqual((len(r["name"]), len(r["instrument"])), (80, 80))

    def test_sql_metacharacters_are_data(self):
        r = self.db.add_run("x'); drop table runs; --", "a\"b", {"k": "v'; drop table runs; --"})
        self.assertEqual(self.db.get_run(r["id"])["name"], "x'); drop table runs; --")
        self.assertEqual(self.db.count_runs(), 1)

    def test_unicode_survives(self):
        r = self.db.add_run("Aleksandra Wiśniewska 🦊 王秀英", "USD/SGD", {"note": "Đặng Thị"})
        self.assertEqual(self.db.get_run(r["id"])["name"], "Aleksandra Wiśniewska 🦊 王秀英")

    def test_file_database_persists_between_connections(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "x.db")                                   # parent folder is created
            db = ldb.Database(path)
            db.add_run("kept", "USD/SGD", {})
            db.close()
            db2 = ldb.Database(path)
            self.assertEqual([r["name"] for r in db2.list_runs()], ["kept"])
            db2.close()


class Snapshots(unittest.TestCase):
    def setUp(self):
        self.db = ldb.Database(":memory:")

    def test_as_of_parsing(self):
        self.assertEqual(ldb.parse_as_of("2026-10-19 14:30:00"), "2026-10-19T14:30:00Z")
        self.assertEqual(ldb.parse_as_of("2026-10-19 (ECB daily fixing)"), "2026-10-19T00:00:00Z")
        self.assertIsNone(ldb.parse_as_of("garbage"))
        self.assertIsNone(ldb.parse_as_of(None))

    def test_failed_and_undated_quotes_are_skipped(self):
        rows = ldb.snapshot_rows(QUOTES)
        self.assertEqual([r["instrument"] for r in rows], ["USD/SGD", "EUR/USD"])
        self.assertEqual(rows[0], dict(instrument="USD/SGD", ts="2026-10-19T14:30:00Z", spot=1.2795, source="yahoo:SGD=X"))

    def test_storing_twice_adds_nothing_new(self):
        rows = ldb.snapshot_rows(QUOTES)
        self.assertEqual(self.db.add_snapshots(rows), 2)
        self.assertEqual(self.db.add_snapshots(rows), 0)
        self.assertEqual(len(self.db.snapshots()), 2)

    def test_filter_order_and_limit(self):
        self.db.add_snapshots([dict(instrument="Gold", ts=f"2026-10-1{d}T00:00:00Z", spot=2000 + d, source="t") for d in range(1, 6)])
        self.db.add_snapshots([dict(instrument="Silver", ts="2026-10-01T00:00:00Z", spot=30, source="t")])
        g = self.db.snapshots("Gold", 3)
        self.assertEqual([r["spot"] for r in g], [2005, 2004, 2003])
        self.assertEqual(len(self.db.snapshots()), 6)

    def test_non_positive_spot_is_never_stored(self):
        self.assertEqual(self.db.add_snapshots([dict(instrument="x", ts="2026-10-01T00:00:00Z", spot=0, source="t"),
                                                dict(instrument="x", ts="2026-10-02T00:00:00Z", spot=-3, source="t")]), 0)
        self.assertEqual(self.db.snapshots(), [])


if __name__ == "__main__":
    unittest.main()
