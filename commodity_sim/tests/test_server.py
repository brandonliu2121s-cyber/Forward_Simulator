"""The Commodity Desk server over real HTTP on a free loopback port with a temporary database."""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from csim import server  # noqa: E402
from csim.db import Database, ValidationError  # noqa: E402


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = Database(os.path.join(cls.tmp.name, "t.db"))
        cls.srv = server.make_server(cls.db, "127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.db.close()
        cls.tmp.cleanup()

    def req(self, method, path, body=None, headers=None, host=None, raw=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        if body is not None or raw is not None:
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        c.request(method, path, body=raw if raw is not None else (json.dumps(body) if body is not None else None), headers=h)
        r = c.getresponse()
        text = r.read().decode()
        c.close()
        try:
            return r.status, json.loads(text), r
        except ValueError:
            return r.status, text, r


class Api(Base):
    M = dict(commodity="wti", seed=4, days=250)

    def test_catalogue_and_health(self):
        s, d, _ = self.req("GET", "/api/commodities")
        self.assertEqual((s, len(d["commodities"]), d["groups"], d["warmup"]), (200, 9, ["Agriculture", "Energy", "Metals"], 300))
        self.assertTrue(self.req("GET", "/api/health")[1]["ok"])
        self.assertEqual(len(self.req("GET", "/api/strategies")[1]["strategies"]), 5)

    def test_market_shape_and_determinism(self):
        s, a, _ = self.req("POST", "/api/market", self.M)
        self.assertEqual(s, 200)
        self.assertEqual((a["total"], a["start_bar"], len(a["bars"]), len(a["dates"]), len(a["scores"])), (550, 300, 550, 550, 550))
        self.assertEqual(set(a["indicators"]) >= {"sma50", "rsi14", "macd_hist", "bb_up"}, True)
        self.assertEqual(self.req("POST", "/api/market", self.M)[1], a)
        self.assertNotEqual(self.req("POST", "/api/market", dict(self.M, seed=5))[1]["bars"], a["bars"])

    def test_analysis_matches_the_signal_series(self):
        _, mk, _ = self.req("POST", "/api/market", self.M)
        s, a, _ = self.req("POST", "/api/analysis", dict(self.M, t=420))
        self.assertEqual(s, 200)
        self.assertAlmostEqual(a["score"], mk["scores"][420], delta=0.3)
        self.assertEqual(self.req("POST", "/api/analysis", dict(self.M, t=10))[1]["signal"], "Hold")

    def test_account_replays_orders(self):
        orders = [dict(id=1, bar=310, side="buy", qty=2), dict(id=2, bar=330, side="sell", qty=2)]
        s, a, _ = self.req("POST", "/api/account", dict(self.M, orders=orders, up_to=360))
        self.assertEqual(s, 200)
        self.assertEqual([f["bar"] for f in a["fills"]], [311, 331])
        self.assertEqual(a["account"]["qty"], 0)
        self.assertEqual(len(a["equity"]), 61)

    def test_backtest_montecarlo_and_sweep(self):
        s, b, _ = self.req("POST", "/api/backtest", dict(self.M, strategy="sma_cross", params=dict(fast=10, slow=50), allow_short=True))
        self.assertEqual(s, 200)
        self.assertIn("metrics", b["buy_hold"])
        self.assertEqual(len(b["equity"]), 250)
        s, mc, _ = self.req("POST", "/api/montecarlo", dict(self.M, strategy="signal", n=10))
        self.assertEqual((s, mc["n"], sum(mc["histogram"]["counts"])), (200, 10, 10))
        s, sw, _ = self.req("POST", "/api/sweep", self.M)
        self.assertEqual((s, len(sw["rows"])), (200, 12))

    def test_bad_input_gets_a_specific_400(self):
        cases = [("/api/market", dict(commodity="nope")), ("/api/market", dict(commodity="wti", days=5)), ("/api/market", dict(commodity="wti", seed="x")),
                 ("/api/market", dict(commodity="wti", seed=1.5)), ("/api/market", {}), ("/api/analysis", dict(self.M, t=99999)),
                 ("/api/account", dict(self.M, orders="x")), ("/api/account", dict(self.M, orders=[dict(bar="a")])), ("/api/account", dict(self.M, up_to=5)),
                 ("/api/backtest", dict(self.M, strategy="nope")), ("/api/backtest", dict(self.M, strategy="sma_cross", params=dict(fast=60, slow=10))),
                 ("/api/backtest", dict(self.M, alloc=50)), ("/api/montecarlo", dict(self.M, n=100000))]
        for path, body in cases:
            s, d, _ = self.req("POST", path, body)
            self.assertEqual(s, 400, (path, body, d))
            self.assertTrue(d["error"])
        self.assertEqual(self.req("POST", "/api/market", raw="{bad")[0], 400)
        self.assertEqual(self.req("POST", "/api/market", raw="[1]")[0], 400)
        self.assertEqual(self.req("GET", "/api/nope")[0], 404)

    def test_saved_runs_crud(self):
        s, d, _ = self.req("POST", "/api/runs", dict(name=" My trade ", kind="trade", commodity="wti", params=dict(self.M, orders=[]), summary=dict(ret=0.01)))
        self.assertEqual((s, d["run"]["name"]), (201, "My trade"))
        rid = d["run"]["id"]
        self.assertIn(rid, [r["id"] for r in self.req("GET", "/api/runs")[1]["runs"]])
        self.assertEqual(self.req("GET", f"/api/runs/{rid}")[1]["run"]["params"]["seed"], 4)
        self.assertEqual(self.req("DELETE", f"/api/runs/{rid}")[1], {"deleted": rid})
        self.assertEqual(self.req("GET", f"/api/runs/{rid}")[0], 404)
        for bad in (dict(name="", kind="trade", commodity="x", params={}), dict(name="x", kind="oops", commodity="x", params={}), dict(name="x", kind="trade", commodity="x", params=[1])):
            self.assertEqual(self.req("POST", "/api/runs", bad)[0], 400)

    def test_the_page_is_served(self):
        s, body, r = self.req("GET", "/")
        self.assertEqual(s, 200)
        self.assertIn("text/html", r.getheader("Content-Type"))
        self.assertEqual(r.getheader("X-Frame-Options"), "DENY")


class Security(Base):
    def test_foreign_host_and_origin_are_refused(self):
        self.assertEqual(self.req("GET", "/api/runs", host="evil.example.com")[0], 403)
        self.assertEqual(self.req("GET", "/api/runs", headers={"Origin": "https://evil.example.com"})[0], 403)
        self.assertEqual(self.req("POST", "/api/market", dict(commodity="wti"), headers={"Origin": "http://localhost:9"})[0], 403)
        self.assertEqual(self.req("GET", "/api/runs", headers={"Origin": f"http://127.0.0.1:{self.port}"})[0], 200)

    def test_only_json_and_no_cors(self):
        self.assertEqual(self.req("POST", "/api/market", raw='{"commodity":"wti"}', headers={"Content-Type": "text/plain"})[0], 415)
        s, _, r = self.req("OPTIONS", "/api/market", headers={"Origin": "https://evil.example.com"})
        self.assertEqual(s, 405)
        self.assertIsNone(r.getheader("Access-Control-Allow-Origin"))

    def test_big_bodies_are_refused(self):
        s, _, _ = self.req("POST", "/api/runs", raw="x", headers={"Content-Length": str(server.MAX_BODY + 1)})
        self.assertEqual(s, 413)

    def test_only_loopback(self):
        with self.assertRaises(ValueError):
            server.make_server(self.db, "0.0.0.0", 0)

    def test_hostile_name_is_returned_as_data(self):
        s, d, _ = self.req("POST", "/api/runs", dict(name="<script>alert(1)</script>", kind="trade", commodity="wti", params={}))
        self.assertEqual(d["run"]["name"], "<script>alert(1)</script>")

    def test_internal_errors_do_not_leak_details(self):
        orig = server.POST_ROUTES["/api/sweep"]
        server.POST_ROUTES["/api/sweep"] = lambda m, b: 1 / 0
        try:
            s, d, _ = self.req("POST", "/api/sweep", dict(commodity="wti"))
        finally:
            server.POST_ROUTES["/api/sweep"] = orig
        self.assertEqual(s, 500)
        self.assertNotIn("division", json.dumps(d))


class DbTests(unittest.TestCase):
    def test_validation_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            db = Database(os.path.join(d, "x", "a.db"))
            r = db.add("n" * 200, "backtest", "gold", {"a": 1}, {"b": 2})
            self.assertEqual(len(r["name"]), 80)
            with self.assertRaises(ValidationError):
                db.add("x", "trade", "gold", {"blob": "y" * 500000})
            db.close()
            self.assertEqual(Database(os.path.join(d, "x", "a.db")).get(r["id"])["params"], {"a": 1})


if __name__ == "__main__":
    unittest.main()
