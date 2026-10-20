"""Forward Desk local server: serves the dashboard and keeps saved runs and price history in a SQLite file.

    python3 server/app.py                      # http://127.0.0.1:8000/  (data in data/forward_desk.db)
    python3 server/app.py --port 0 --db /tmp/x.db     # pick a free port, other database file
    python3 server/app.py --auto-refresh 60    # also store live quotes every 60 minutes while it runs

It listens on the loopback address only and has no accounts: anyone who can reach 127.0.0.1 on your machine can use it.
Requests are checked against DNS-rebinding and cross-site attacks (Host and Origin must be this server, JSON bodies only).
Educational use only: delayed, unofficial prices and a simplified model; not for trading decisions.

API (JSON):  GET /api/health  ·  GET /api/prices/latest  ·  GET/POST /api/runs  ·  GET/DELETE /api/runs/<id>  ·  GET /api/snapshots?instrument=&limit=
             POST /api/snapshots/refresh {"provider": "yahoo" | "frankfurter"}
"""
import argparse
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("python", "dev"):
    sys.path.insert(0, os.path.join(ROOT, sub))
import build_dashboard  # noqa: E402
import live_data  # noqa: E402
from local_db import DEFAULT_PATH, Database, ValidationError, snapshot_rows  # noqa: E402

MAX_BODY = 1_200_000
LOOPBACK = ("127.0.0.1", "localhost", "::1")
RUN_ID = re.compile(r"^/api/runs/(\d{1,12})$")


def refresh_prices(db, provider="yahoo", fetch_all=live_data.fetch_all):
    """Fetch live quotes and store them. -> dict(stored, quotes, failed)."""
    quotes = fetch_all(provider)
    ok = sum(1 for q in quotes.values() if q["price"] is not None)
    return dict(stored=db.add_snapshots(snapshot_rows(quotes)), quotes=ok, failed=len(quotes) - ok, provider=provider)


def make_server(db, host="127.0.0.1", port=8000, fetch_all=live_data.fetch_all, page=None, fetch_on_open=True):
    if host not in LOOPBACK:
        raise ValueError("The local server only listens on the loopback address (127.0.0.1).")
    page = page or (lambda: build_dashboard.standalone(build_dashboard.fragment()))

    class Handler(BaseHTTPRequestHandler):
        server_version = "ForwardDesk/1"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass                                                   # quiet; errors are returned to the caller

        # ---- plumbing
        def _send(self, status, body=b"", ctype="application/json", extra=None):
            data = body if isinstance(body, bytes) else json.dumps(body, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _err(self, status, message):
            self._send(status, {"error": message})

        def _allowed_hosts(self):
            port = self.server.server_address[1]
            names = {f"{h}:{port}" for h in ("127.0.0.1", "localhost")} | {f"[::1]:{port}"}
            return names | ({"127.0.0.1", "localhost"} if port == 80 else set())

        def _guard(self):
            """Reject DNS-rebinding (foreign Host) and cross-site requests (foreign Origin). -> True if the request may proceed."""
            if (self.headers.get("Host") or "").lower() not in self._allowed_hosts():
                self._err(403, "Unexpected Host header.")
                return False
            origin = self.headers.get("Origin")
            if origin and origin.lower() not in {f"http://{h}" for h in self._allowed_hosts()}:
                self._err(403, "Cross-site requests are not allowed.")
                return False
            return True

        def _body(self):
            if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
                self._err(415, "Send JSON (Content-Type: application/json).")
                return None
            try:
                n = int(self.headers.get("Content-Length") or "")
            except ValueError:
                self._err(411, "Content-Length is required.")
                return None
            if n < 0 or n > MAX_BODY:
                self._err(413, "That request is too large.")
                return None
            try:
                return json.loads(self.rfile.read(n).decode("utf-8") or "null")
            except (ValueError, UnicodeDecodeError):
                self._err(400, "The request body is not valid JSON.")
                return None

        # ---- routes
        def do_GET(self):
            if not self._guard():
                return
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                return self._send(200, page().encode("utf-8"), "text/html; charset=utf-8")
            if url.path == "/api/health":
                return self._send(200, {"ok": True, "version": 1, "runs": db.count_runs(), "fetch_on_open": bool(fetch_on_open)})
            if url.path == "/api/prices/latest":
                return self._send(200, {"prices": db.latest_snapshots()})
            if url.path == "/api/runs":
                return self._send(200, {"runs": db.list_runs()})
            m = RUN_ID.match(url.path)
            if m:
                run = db.get_run(m.group(1))
                return self._send(200, {"run": run}) if run else self._err(404, "That run no longer exists.")
            if url.path == "/api/snapshots":
                q = parse_qs(url.query)
                try:
                    limit = int((q.get("limit") or ["500"])[0])
                except ValueError:
                    return self._err(400, "limit must be a number.")
                return self._send(200, {"snapshots": db.snapshots((q.get("instrument") or [None])[0], limit)})
            self._err(404, "Not found.")

        def do_POST(self):
            if not self._guard():
                return
            path = urlparse(self.path).path
            if path not in ("/api/runs", "/api/snapshots/refresh"):
                return self._err(404, "Not found.")
            body = self._body()
            if body is None:
                return
            if path == "/api/runs":
                if not isinstance(body, dict):
                    return self._err(400, "Expected a JSON object.")
                try:
                    run = db.add_run(body.get("name"), body.get("instrument"), body.get("session"), body.get("summary"))
                except ValidationError as exc:
                    return self._err(400, str(exc))
                return self._send(201, {"run": run})
            provider = (body or {}).get("provider", "yahoo") if isinstance(body, dict) else "yahoo"
            if provider not in ("yahoo", "frankfurter"):
                return self._err(400, "provider must be yahoo or frankfurter.")
            try:
                return self._send(200, refresh_prices(db, provider, fetch_all))
            except Exception as exc:  # the feeds are third-party; report instead of crashing the handler
                return self._err(502, f"Could not fetch prices: {type(exc).__name__}")

        def do_DELETE(self):
            if not self._guard():
                return
            m = RUN_ID.match(urlparse(self.path).path)
            if not m:
                return self._err(404, "Not found.")
            if db.delete_run(m.group(1)):
                return self._send(200, {"deleted": int(m.group(1))})
            self._err(404, "That run no longer exists.")

        def do_OPTIONS(self):                                      # no CORS: browsers on other origins are refused
            self._err(405, "Cross-origin requests are not supported.")

    return ThreadingHTTPServer((host, port), Handler)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1", help="loopback only (default 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8000, help="0 picks a free port")
    ap.add_argument("--db", default=DEFAULT_PATH, help="SQLite file (default data/forward_desk.db)")
    ap.add_argument("--no-fetch-on-open", action="store_true", help="the dashboard will not fetch fresh prices when it opens (it still shows stored ones)")
    ap.add_argument("--auto-refresh", type=float, metavar="MINUTES", help="store live quotes every MINUTES while the server runs")
    a = ap.parse_args(argv)
    db = Database(a.db)
    try:
        srv = make_server(db, a.host, a.port, fetch_on_open=not a.no_fetch_on_open)
    except (ValueError, OSError) as exc:
        print(f"Could not start: {exc}", file=sys.stderr)
        return 1
    if a.auto_refresh:
        stop = threading.Event()

        def loop():
            while not stop.wait(max(1.0, a.auto_refresh * 60)):
                try:
                    r = refresh_prices(db)
                    print(f"price refresh: {r['stored']} new snapshot(s), {r['failed']} failed", flush=True)
                except Exception as exc:  # keep the loop alive
                    print(f"price refresh failed: {type(exc).__name__}", file=sys.stderr, flush=True)
        threading.Thread(target=loop, daemon=True).start()
    print(f"Forward Desk running at http://{a.host}:{srv.server_address[1]}/   (database: {db.path})   Ctrl+C to stop", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
