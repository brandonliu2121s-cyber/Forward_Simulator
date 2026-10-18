"""Unit tests for live_data.py using canned payloads (no network).

These prove the parsing / error handling / unit conversion logic. They do NOT prove the real feeds are
reachable or still return this shape: run refresh_live.py on a machine with internet to check that.
Run from the repo root:  python3 -m unittest discover -s tests -t .
"""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))

import live_data as ld  # noqa: E402
from instruments import ALL, LIVE_SYMBOLS, by_name  # noqa: E402

YAHOO_OK = {"chart": {"result": [{"meta": {"regularMarketPrice": 1.1634, "regularMarketTime": 1760000000}}], "error": None}}
FRANK_OK = {"amount": 1.0, "base": "USD", "date": "2026-10-16", "rates": {"SGD": 1.2871}}


class Parsers(unittest.TestCase):
    def test_yahoo_ok(self):
        price, as_of = ld.parse_yahoo_chart(YAHOO_OK)
        self.assertEqual(price, 1.1634)
        self.assertEqual(as_of, "2025-10-09 08:53:20")

    def test_yahoo_provider_error(self):
        with self.assertRaises(ld.FeedError):
            ld.parse_yahoo_chart({"chart": {"result": None, "error": {"code": "Not Found"}}})

    def test_yahoo_malformed(self):
        for bad in ({}, {"chart": {"result": []}}, {"chart": {"result": [{"meta": {}}]}}, None):
            with self.assertRaises(ld.FeedError):
                ld.parse_yahoo_chart(bad)

    def test_rejects_bad_prices(self):
        for p in (0, -1.2, float("nan"), float("inf")):
            payload = {"chart": {"result": [{"meta": {"regularMarketPrice": p, "regularMarketTime": 1760000000}}]}}
            with self.assertRaises(ld.FeedError):
                ld.parse_yahoo_chart(payload)

    def test_frankfurter(self):
        price, as_of = ld.parse_frankfurter(FRANK_OK, "SGD")
        self.assertEqual(price, 1.2871)
        self.assertIn("2026-10-16", as_of)
        with self.assertRaises(ld.FeedError):
            ld.parse_frankfurter(FRANK_OK, "JPY")


class Fetching(unittest.TestCase):
    def test_every_instrument_has_a_symbol(self):
        self.assertEqual({i["name"] for i in ALL}, set(LIVE_SYMBOLS))

    def test_copper_converted_from_usd_per_lb_to_usd_per_tonne(self):
        payload = {"chart": {"result": [{"meta": {"regularMarketPrice": 4.50, "regularMarketTime": 1760000000}}]}}
        r = ld.fetch_one(by_name("Copper"), "yahoo", get=lambda url: payload)
        self.assertAlmostEqual(r["price"], 4.50 * 2204.62262, places=6)
        self.assertEqual(r["status"], "ok")
        self.assertTrue(r["source"].startswith("yahoo:HG=F"))

    def test_symbol_is_url_encoded_and_used(self):
        seen = []
        ld.fetch_one(by_name("Gold"), "yahoo", get=lambda url: seen.append(url) or YAHOO_OK)
        self.assertIn("GC%3DF", seen[0])

    def test_failure_is_contained_per_instrument(self):
        def flaky(url):
            if "EURUSD" in url:
                raise ld.FeedError("boom")
            return YAHOO_OK
        res = ld.fetch_all("yahoo", get=flaky)
        self.assertIsNone(res["EUR/USD"]["price"])
        self.assertTrue(res["EUR/USD"]["status"].startswith("error:"))
        self.assertEqual(res["Gold"]["status"], "ok")
        self.assertEqual(len(res), len(ALL))

    def test_frankfurter_unsupported_cases(self):
        res = ld.fetch_all("frankfurter", get=lambda url: FRANK_OK)
        self.assertEqual(res["Gold"]["status"], "unsupported by this provider")
        self.assertEqual(res["USD/CNH"]["status"], "unsupported by this provider")
        self.assertEqual(res["USD/SGD"]["price"], 1.2871)

    def test_unknown_provider(self):
        r = ld.fetch_one(by_name("Gold"), "nope", get=lambda url: {})
        self.assertTrue(r["status"].startswith("error:"))


class Snapshot(unittest.TestCase):
    def test_round_trip_and_missing_file(self):
        res = {"Gold": dict(price=4000.5, as_of="x", source="s", status="ok")}
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "snap.json")
            ld.write_snapshot(res, p)
            doc = ld.read_snapshot(p)
            self.assertEqual(doc["quotes"]["Gold"]["price"], 4000.5)
            self.assertIn("fetched_utc", doc)
            self.assertIsNone(ld.read_snapshot(os.path.join(d, "missing.json")))
            with open(p, "w") as fh:
                fh.write("not json")
            self.assertIsNone(ld.read_snapshot(p))


if __name__ == "__main__":
    unittest.main()
