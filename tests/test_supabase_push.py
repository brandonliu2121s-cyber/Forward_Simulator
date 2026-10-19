"""Supabase snapshot push (python/supabase_push.py) with a fake HTTP post: no network, no credentials."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))
import supabase_push as sp  # noqa: E402

QUOTES = {
    "USD/SGD": dict(price=1.2795, as_of="2026-10-19 14:30:00", source="yahoo:SGD=X", status="ok"),
    "EUR/USD": dict(price=1.1629, as_of="2026-10-19 (ECB daily fixing)", source="frankfurter:EUR/USD", status="ok"),
    "Gold": dict(price=None, as_of=None, source="yahoo:GC=F", status="error: boom"),
    "Odd": dict(price=1.0, as_of="not a date", source="x", status="ok"),
}


class Push(unittest.TestCase):
    def test_as_of_parsing(self):
        self.assertEqual(sp.parse_as_of("2026-10-19 14:30:00"), "2026-10-19T14:30:00Z")
        self.assertEqual(sp.parse_as_of("2026-10-19 (ECB daily fixing)"), "2026-10-19T00:00:00Z")
        self.assertIsNone(sp.parse_as_of("garbage"))
        self.assertIsNone(sp.parse_as_of(None))

    def test_failed_and_undated_quotes_are_skipped(self):
        rows = sp.rows_from_quotes(QUOTES)
        self.assertEqual([r["instrument"] for r in rows], ["USD/SGD", "EUR/USD"])
        self.assertEqual(rows[0], dict(instrument="USD/SGD", ts="2026-10-19T14:30:00Z", spot=1.2795, source="yahoo:SGD=X"))

    def test_push_builds_an_idempotent_request(self):
        seen = {}
        n = sp.push(QUOTES, url="https://abcdefghij.supabase.co/", key="svc", post=lambda u, h, b: seen.update(u=u, h=h, b=b))
        self.assertEqual(n, 2)
        self.assertEqual(seen["u"], "https://abcdefghij.supabase.co/rest/v1/price_snapshots?on_conflict=instrument,ts,source")
        self.assertIn("ignore-duplicates", seen["h"]["Prefer"])
        self.assertEqual(seen["h"]["Authorization"], "Bearer svc")
        self.assertEqual(len(seen["b"]), 2)

    def test_nothing_to_push_makes_no_request(self):
        def boom(*a):
            raise AssertionError("should not post")
        self.assertEqual(sp.push({"Gold": QUOTES["Gold"]}, url="https://abcdefghij.supabase.co", key="k", post=boom), 0)

    def test_missing_config_and_bad_url_are_refused(self):
        old = {k: os.environ.pop(k, None) for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY")}
        try:
            with self.assertRaises(sp.PushError):
                sp.push(QUOTES)
            with self.assertRaises(sp.PushError):
                sp.push(QUOTES, url="https://evil.example.com", key="k", post=lambda *a: None)
        finally:
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v

    def test_http_errors_are_reported(self):
        def fail(*a):
            raise sp.PushError("Supabase answered 401: bad key")
        with self.assertRaises(sp.PushError):
            sp.push(QUOTES, url="https://abcdefghij.supabase.co", key="k", post=fail)


if __name__ == "__main__":
    unittest.main()
