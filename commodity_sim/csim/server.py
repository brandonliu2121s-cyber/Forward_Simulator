"""Commodity Desk local server: serves the web app and a JSON API, keeps saved runs in SQLite.

    python3 commodity_sim/app.py                 # http://127.0.0.1:8010/   (data in commodity_sim/data/commodity_desk.db)
    python3 commodity_sim/app.py --port 0 --db /tmp/x.db

Loopback only, no accounts. Host and Origin are checked (DNS rebinding, cross-site pages) and POST bodies must be JSON.
Educational use only: simulated prices, no advice.
"""
import argparse
import collections
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import analysis, backtest, commodities, indicators, simulator
from .account import run_account
from .db import DEFAULT_PATH, Database, ValidationError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
MAX_BODY = 600_000
LOOPBACK = ("127.0.0.1", "localhost", "::1")
RUN_ID = re.compile(r"^/api/runs/(\d{1,12})$")
SHOWN = ("sma20", "sma50", "sma200", "bb_up", "bb_low", "rsi14", "macd", "macd_signal", "macd_hist", "atr14")


class Markets:
    """Small LRU cache of generated markets: (commodity, seed, days) -> bars, events, indicators, scores."""

    def __init__(self, size=24):
        self.size, self.lock, self.items = size, threading.Lock(), collections.OrderedDict()

    def get(self, key, seed, days):
        k = (key, seed, days)
        with self.lock:
            if k in self.items:
                self.items.move_to_end(k)
                return self.items[k]
        sim = simulator.simulate(key, seed, backtest.WARMUP + days)
        ind = indicators.compute(sim["bars"])
        m = dict(sim=sim, ind=ind, scores=analysis.signal_series(ind, sim["bars"], key), key=key, seed=seed, days=days)
        with self.lock:
            self.items[k] = m
            while len(self.items) > self.size:
                self.items.popitem(last=False)
        return m


def _int(body, name, default, lo, hi):
    v = body.get(name, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != int(v):
        raise ValueError(f"{name} must be a whole number.")
    if not lo <= v <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi}.")
    return int(v)


def _num(body, name, default, lo, hi):
    v = body.get(name, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        raise ValueError(f"{name} must be a number.")
    if not lo <= v <= hi:
        raise ValueError(f"{name} must be between {lo:g} and {hi:g}.")
    return float(v)


def market_args(body):
    key = body.get("commodity")
    if not isinstance(key, str):
        raise ValueError("commodity is required.")
    commodities.get(key)
    return key, _int(body, "seed", 1, 0, 2 ** 31 - 1), _int(body, "days", 250, 60, 750)


def _round(series, nd=4):
    return [None if v is None else round(v, nd) for v in series]


def api_market(markets, body):
    key, seed, days = market_args(body)
    m = markets.get(key, seed, days)
    sim, prof = m["sim"], commodities.get(key)
    return dict(commodity=commodities.public_list()[[c["key"] for c in commodities.COMMODITIES].index(key)], seed=seed, days=days, start_bar=backtest.WARMUP, total=len(sim["bars"]),
                dates=sim["dates"], bars=sim["bars"], events=sim["events"], indicators={k: _round(m["ind"][k]) for k in SHOWN}, scores=m["scores"],
                thresholds=dict(buy=analysis.BUY_AT, sell=analysis.SELL_AT), group=prof["group"])


def api_analysis(markets, body):
    key, seed, days = market_args(body)
    m = markets.get(key, seed, days)
    t = _int(body, "t", backtest.WARMUP, 0, len(m["sim"]["bars"]) - 1)
    return analysis.analyze(m["ind"], m["sim"]["bars"], t, key)


def api_account(markets, body):
    key, seed, days = market_args(body)
    m = markets.get(key, seed, days)
    orders = body.get("orders", [])
    if not isinstance(orders, list) or len(orders) > 2000 or not all(isinstance(o, dict) for o in orders):
        raise ValueError("orders must be a list of objects.")
    for o in orders:
        for f in ("bar", "qty", "cancel_bar"):
            if o.get(f) is not None and (isinstance(o[f], bool) or not isinstance(o[f], (int, float))):
                raise ValueError(f"order {f} must be a number.")
        if o.get("price") is not None and (isinstance(o["price"], bool) or not isinstance(o["price"], (int, float))):
            raise ValueError("order price must be a number.")
    up_to = _int(body, "up_to", backtest.WARMUP, backtest.WARMUP, len(m["sim"]["bars"]) - 1)
    costs = body.get("costs")
    if costs is not None and not isinstance(costs, dict):
        raise ValueError("costs must be an object.")
    r = run_account(m["sim"]["bars"], commodities.get(key)["lot"], orders, backtest.WARMUP, up_to, _num(body, "cash", 100000, 1000, 1e9), costs, _num(body, "max_leverage", 3, 1, 10))
    r["fills"] = r["fills"][-500:]
    return r


def _bt_args(body):
    key, seed, days = market_args(body)
    strat = body.get("strategy", "signal")
    if strat not in backtest.STRATEGIES:
        raise ValueError("Unknown strategy.")
    params = body.get("params") or {}
    costs = body.get("costs")
    if not isinstance(params, dict) or (costs is not None and not isinstance(costs, dict)):
        raise ValueError("params and costs must be objects.")
    alloc = body.get("alloc", 0.5)
    if isinstance(alloc, bool) or not isinstance(alloc, (int, float)) or not 0.05 <= alloc <= 2.0:
        raise ValueError("Position size must be between 5% and 200% of equity.")
    return key, seed, days, strat, params, costs, _num(body, "cash", 100000, 1000, 1e9), float(alloc), bool(body.get("allow_short", False))


def api_backtest(markets, body):
    key, seed, days, strat, params, costs, cash, alloc, short = _bt_args(body)
    m = markets.get(key, seed, days)
    r = backtest.compare(m["sim"]["bars"], m["ind"], key, strat, params, backtest.WARMUP, len(m["sim"]["bars"]) - 1, cash, costs, alloc, short)
    r["fills"] = r["fills"][-300:]
    return r


def api_montecarlo(markets, body):
    key, _, days, strat, params, costs, cash, alloc, short = _bt_args(body)
    return backtest.monte_carlo(key, strat, params, _int(body, "n", 100, 5, 300), days, _int(body, "seed0", 1, 0, 2 ** 31 - 1000), cash, costs, alloc, short)


def api_sweep(markets, body):
    key, seed, days, _, _, costs, cash, alloc, short = _bt_args(body)
    m = markets.get(key, seed, days)
    return backtest.sweep_sma(m["sim"]["bars"], m["ind"], key, backtest.WARMUP, len(m["sim"]["bars"]) - 1, cash, costs, alloc, short)


POST_ROUTES = {"/api/market": api_market, "/api/analysis": api_analysis, "/api/account": api_account, "/api/backtest": api_backtest, "/api/montecarlo": api_montecarlo, "/api/sweep": api_sweep}


def make_server(db, host="127.0.0.1", port=8010):
    if host not in LOOPBACK:
        raise ValueError("The server only listens on the loopback address (127.0.0.1).")
    markets = Markets()

    class Handler(BaseHTTPRequestHandler):
        server_version = "CommodityDesk/1"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        def _send(self, status, body=b"", ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            for k, v in (("Content-Type", ctype), ("Content-Length", str(len(data))), ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                         ("X-Frame-Options", "DENY"), ("Referrer-Policy", "no-referrer")):
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _err(self, status, message):
            self._send(status, {"error": message})

        def _hosts(self):
            port = self.server.server_address[1]
            return {f"{h}:{port}" for h in ("127.0.0.1", "localhost")} | {f"[::1]:{port}"}

        def _guard(self):
            if (self.headers.get("Host") or "").lower() not in self._hosts():
                self._err(403, "Unexpected Host header.")
                return False
            origin = self.headers.get("Origin")
            if origin and origin.lower() not in {f"http://{h}" for h in self._hosts()}:
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
                d = json.loads(self.rfile.read(n).decode("utf-8") or "null")
            except (ValueError, UnicodeDecodeError):
                self._err(400, "The request body is not valid JSON.")
                return None
            if not isinstance(d, dict):
                self._err(400, "Expected a JSON object.")
                return None
            return d

        def do_GET(self):
            if not self._guard():
                return
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                try:
                    with open(os.path.join(WEB, "index.html"), "rb") as fh:
                        return self._send(200, fh.read(), "text/html; charset=utf-8")
                except OSError:
                    return self._err(500, "The web page is missing.")
            if path == "/favicon.ico":
                return self._send(204)
            if path == "/api/health":
                return self._send(200, {"ok": True, "app": "commodity-desk", "version": 1})
            if path == "/api/commodities":
                return self._send(200, {"groups": list(commodities.GROUPS), "commodities": commodities.public_list(), "warmup": backtest.WARMUP})
            if path == "/api/strategies":
                return self._send(200, {"strategies": [dict(key=k, label=v["label"], params=v["params"]) for k, v in backtest.STRATEGIES.items()]})
            if path == "/api/runs":
                return self._send(200, {"runs": db.list()})
            m = RUN_ID.match(path)
            if m:
                run = db.get(m.group(1))
                return self._send(200, {"run": run}) if run else self._err(404, "That saved run no longer exists.")
            self._err(404, "Not found.")

        def do_POST(self):
            if not self._guard():
                return
            path = urlparse(self.path).path
            if path not in POST_ROUTES and path != "/api/runs":
                return self._err(404, "Not found.")
            body = self._body()
            if body is None:
                return
            try:
                if path == "/api/runs":
                    run = db.add(body.get("name"), body.get("kind"), body.get("commodity"), body.get("params"), body.get("summary"))
                    return self._send(201, {"run": run})
                return self._send(200, POST_ROUTES[path](markets, body))
            except ValueError as exc:                          # includes ValidationError: safe, specific messages
                return self._err(400, str(exc))
            except Exception as exc:                           # a bug, not the caller's fault: say little, keep the server up
                print(f"internal error on {path}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                return self._err(500, "Something went wrong on the server.")

        def do_DELETE(self):
            if not self._guard():
                return
            m = RUN_ID.match(urlparse(self.path).path)
            if not m:
                return self._err(404, "Not found.")
            if db.delete(m.group(1)):
                return self._send(200, {"deleted": int(m.group(1))})
            self._err(404, "That saved run no longer exists.")

        def do_OPTIONS(self):
            self._err(405, "Cross-origin requests are not supported.")

    return ThreadingHTTPServer((host, port), Handler)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8010, help="0 picks a free port")
    ap.add_argument("--db", default=DEFAULT_PATH)
    a = ap.parse_args(argv)
    db = Database(a.db)
    try:
        srv = make_server(db, a.host, a.port)
    except (ValueError, OSError) as exc:
        print(f"Could not start: {exc}", file=sys.stderr)
        return 1
    print(f"Commodity Desk running at http://{a.host}:{srv.server_address[1]}/   (database: {db.path})   Ctrl+C to stop", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()
        db.close()
    return 0
