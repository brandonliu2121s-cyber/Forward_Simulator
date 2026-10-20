"""Local server (server/app.py) over real HTTP on a free loopback port with a temporary database. No internet: prices come from a fake feed."""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
import app  # noqa: E402
from local_db import Database  # noqa: E402

FEED = {"USD/SGD": dict(price=1.2795, as_of="2026-10-19 14:30:00", source="yahoo:SGD=X", status="ok"),
        "Gold": dict(price=None, as_of=None, source="yahoo:GC=F", status="error: boom")}


class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = Database(os.path.join(cls.tmp.name, "t.db"))
        cls.srv = app.make_server(cls.db, "127.0.0.1", 0, fetch_all=lambda provider: FEED, page=lambda: "<html>page</html>")
        cls.port = cls.srv.server_address[1]
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.db.close()
        cls.tmp.cleanup()

    def req(self, method, path, body=None, headers=None, host=None, raw=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        if body is not None or raw is not None:
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        data = raw if raw is not None else (json.dumps(body) if body is not None else None)
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        text = r.read().decode()
        c.close()
        try:
            return r.status, json.loads(text), r
        except ValueError:
            return r.status, text, r


class Api(ServerCase):
    def test_page_and_health(self):
        s, body, r = self.req("GET", "/")
        self.assertEqual((s, body), (200, "<html>page</html>"))
        self.assertIn("text/html", r.getheader("Content-Type"))
        self.assertEqual(r.getheader("X-Frame-Options"), "DENY")
        s, body, _ = self.req("GET", "/api/health")
        self.assertTrue(s == 200 and body["ok"] is True)

    def test_run_crud(self):
        s, body, _ = self.req("POST", "/api/runs", {"name": " Wide spread ", "instrument": "USD/SGD", "session": {"format": "forward-desk-session"}, "summary": {"pnl": -1.5}})
        self.assertEqual(s, 201)
        run = body["run"]
        self.assertEqual(run["name"], "Wide spread")
        s, body, _ = self.req("GET", "/api/runs")
        self.assertIn(run["id"], [r["id"] for r in body["runs"]])
        self.assertNotIn("session", body["runs"][0])
        s, body, _ = self.req("GET", f"/api/runs/{run['id']}")
        self.assertEqual(body["run"]["session"], {"format": "forward-desk-session"})
        s, body, _ = self.req("DELETE", f"/api/runs/{run['id']}")
        self.assertEqual((s, body), (200, {"deleted": run["id"]}))
        self.assertEqual(self.req("GET", f"/api/runs/{run['id']}")[0], 404)
        self.assertEqual(self.req("DELETE", f"/api/runs/{run['id']}")[0], 404)

    def test_bad_input_gets_a_clear_4xx(self):
        self.assertEqual(self.req("POST", "/api/runs", {"name": "", "instrument": "x", "session": {}})[0], 400)
        self.assertEqual(self.req("POST", "/api/runs", {"name": "x", "instrument": "x", "session": "nope"})[0], 400)
        self.assertEqual(self.req("POST", "/api/runs", raw="{not json")[0], 400)
        self.assertEqual(self.req("POST", "/api/runs", [1, 2])[0], 400)
        self.assertEqual(self.req("GET", "/api/runs/abc")[0], 404)
        self.assertEqual(self.req("GET", "/api/runs/1%3B%20drop%20table%20runs")[0], 404)
        self.assertEqual(self.req("GET", "/api/nope")[0], 404)
        self.assertEqual(self.req("GET", "/api/snapshots?limit=x")[0], 400)

    def test_big_bodies_and_missing_length_are_refused(self):
        s, body, _ = self.req("POST", "/api/runs", raw="x" * 10, headers={"Content-Length": str(app.MAX_BODY + 1)})
        self.assertEqual(s, 413)

    def test_latest_prices_endpoint_and_fetch_on_open_flag(self):
        self.db.add_snapshots([dict(instrument="Copper", ts="2026-10-19T14:30:00Z", spot=9500.5, source="t")])
        s, body, _ = self.req("GET", "/api/prices/latest")
        self.assertEqual((s, body["prices"]["Copper"]["spot"], body["prices"]["Copper"]["ts"]), (200, 9500.5, "2026-10-19T14:30:00Z"))
        self.assertIs(self.req("GET", "/api/health")[1]["fetch_on_open"], True)

    def test_snapshots_refresh_and_read(self):
        s, body, _ = self.req("POST", "/api/snapshots/refresh", {"provider": "yahoo"})
        self.assertEqual((s, body["stored"], body["quotes"], body["failed"]), (200, 1, 1, 1))
        self.assertEqual(self.req("POST", "/api/snapshots/refresh", {"provider": "yahoo"})[1]["stored"], 0)    # same timestamp: no duplicates
        s, body, _ = self.req("GET", "/api/snapshots?instrument=USD/SGD")
        self.assertEqual([(r["instrument"], r["spot"]) for r in body["snapshots"]], [("USD/SGD", 1.2795)])
        self.assertEqual(self.req("POST", "/api/snapshots/refresh", {"provider": "evil"})[0], 400)


class Security(ServerCase):
    def test_foreign_host_header_is_refused_dns_rebinding(self):
        self.assertEqual(self.req("GET", "/api/runs", host="evil.example.com")[0], 403)
        self.assertEqual(self.req("GET", "/", host=f"attacker.test:{self.port}")[0], 403)

    def test_cross_site_origin_is_refused(self):
        self.assertEqual(self.req("GET", "/api/runs", headers={"Origin": "https://evil.example.com"})[0], 403)
        self.assertEqual(self.req("POST", "/api/runs", {"name": "x", "instrument": "x", "session": {}}, headers={"Origin": "http://localhost:9999"})[0], 403)
        self.assertEqual(self.req("GET", "/api/runs", headers={"Origin": f"http://localhost:{self.port}"})[0], 200)   # our own origin is fine

    def test_simple_cross_site_form_posts_are_refused(self):
        s, _, _ = self.req("POST", "/api/runs", raw='{"name":"x","instrument":"x","session":{}}', headers={"Content-Type": "text/plain"})
        self.assertEqual(s, 415)
        s, _, _ = self.req("POST", "/api/runs", raw="name=x", headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(s, 415)

    def test_no_cors_preflight(self):
        s, _, r = self.req("OPTIONS", "/api/runs", headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"})
        self.assertNotEqual(s, 200)
        self.assertIsNone(r.getheader("Access-Control-Allow-Origin"))

    def test_only_loopback_can_be_bound(self):
        with self.assertRaises(ValueError):
            app.make_server(self.db, "0.0.0.0", 0)
        with self.assertRaises(ValueError):
            app.make_server(self.db, "192.168.1.5", 0)

    def test_a_hostile_name_is_returned_as_data(self):
        s, body, _ = self.req("POST", "/api/runs", {"name": "<script>alert(1)</script>", "instrument": "x", "session": {}})
        self.assertEqual(body["run"]["name"], "<script>alert(1)</script>")


class FetchOnOpenOff(unittest.TestCase):
    def test_health_reports_it(self):
        db = Database(":memory:")
        srv = app.make_server(db, "127.0.0.1", 0, fetch_on_open=False, page=lambda: "x")
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
            c.request("GET", "/api/health", headers={"Host": f"127.0.0.1:{srv.server_address[1]}"})
            self.assertIs(json.loads(c.getresponse().read())["fetch_on_open"], False)
        finally:
            srv.shutdown()
            srv.server_close()


class Refresh(unittest.TestCase):
    def test_refresh_prices_reports_counts(self):
        db = Database(":memory:")
        r = app.refresh_prices(db, "yahoo", lambda p: FEED)
        self.assertEqual((r["stored"], r["quotes"], r["failed"]), (1, 1, 1))

    def test_refresh_live_cli_store_flag_writes_the_local_database(self):
        sys.path.insert(0, os.path.join(ROOT, "python"))
        import refresh_live
        with tempfile.TemporaryDirectory() as d:
            refresh_live.fetch_all = lambda provider: FEED
            code = refresh_live.main(["--no-rebuild", "--store", "--db", os.path.join(d, "s.db"), "--snapshot", os.path.join(d, "snap.json")])
            self.assertEqual(code, 0)
            db = Database(os.path.join(d, "s.db"))
            self.assertEqual([r["instrument"] for r in db.snapshots()], ["USD/SGD"])
            db.close()


if __name__ == "__main__":
    unittest.main()
