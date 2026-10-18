"""Live spot-price snapshot for the forwards market-making simulator (stdlib only, no extra installs).

Data flow:  fetch_all() -> write_snapshot() -> live_snapshot.json -> build_simulator.py bakes it into the
workbook's `Live` sheet.  Nothing here streams: it is a point-in-time snapshot that you refresh on demand.

Providers
  yahoo        FX + commodity front-month futures via Yahoo Finance's unofficial chart endpoint (keyless,
               usually ~15 min delayed, may rate-limit or change without notice).
  frankfurter  FX only, ECB daily reference rates from api.frankfurter.app (keyless, once-a-day, so NOT intraday).
               CNH and commodities are reported as 'unsupported'.

Rates (USD/EUR/... interest rates, convenience yields) are NOT fetched: they stay manual on the Instruments sheet.
All data is for education/demonstration only and must not be used for trading decisions.
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from instruments import ALL, LIVE_SYMBOLS, by_name

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
FRANKFURTER_URL = "https://api.frankfurter.app/latest?from={base}&to={quote}"
UA = "Mozilla/5.0 (forwards-market-making-simulator; educational use)"


class FeedError(Exception):
    """Any problem getting or understanding a quote (network, HTTP, malformed payload, bad value)."""


def http_get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # network, HTTP error, bad JSON: report uniformly
        raise FeedError(f"{type(exc).__name__}: {exc}") from exc


def _utc(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_yahoo_chart(payload):
    """-> (price, as_of_utc_string). Raises FeedError on any unexpected shape."""
    try:
        chart = payload["chart"]
        if chart.get("error"):
            raise FeedError(f"provider error: {chart['error']}")
        meta = chart["result"][0]["meta"]
        price, ts = float(meta["regularMarketPrice"]), int(meta["regularMarketTime"])
    except FeedError:
        raise
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise FeedError(f"unexpected Yahoo payload: {exc!r}") from exc
    return _check(price), _utc(ts)


def parse_frankfurter(payload, quote_ccy):
    """-> (price, as_of). `price` = units of quote_ccy per 1 base (matches 'BASE/QUOTE' convention)."""
    try:
        price, date = float(payload["rates"][quote_ccy]), str(payload["date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FeedError(f"unexpected Frankfurter payload: {exc!r}") from exc
    return _check(price), date + " (ECB daily fixing)"


def _check(price):
    if not price > 0 or price != price or price == float("inf"):
        raise FeedError(f"non-positive or non-finite price: {price}")
    return price


def fetch_one(inst, provider, get=http_get_json):
    """-> dict(price, as_of, source, status). Never raises: failures become status='error: ...'."""
    out = dict(price=None, as_of=None, source=provider, status="ok")
    try:
        if provider == "yahoo":
            symbol, scale = LIVE_SYMBOLS[inst["name"]]
            price, as_of = parse_yahoo_chart(get(YAHOO_URL.format(symbol=urllib.parse.quote(symbol))))
            out.update(price=_check(price * scale), as_of=as_of, source=f"yahoo:{symbol}")
        elif provider == "frankfurter":
            if inst["type"] != "FX" or inst["pnl"] == "CNH" or inst["unit"] == "CNH":
                out["status"] = "unsupported by this provider"
                return out
            url = FRANKFURTER_URL.format(base=inst["unit"], quote=inst["pnl"])
            price, as_of = parse_frankfurter(get(url), inst["pnl"])
            out.update(price=price, as_of=as_of, source=f"frankfurter:{inst['unit']}/{inst['pnl']}")
        else:
            raise FeedError(f"unknown provider {provider!r}")
    except FeedError as exc:
        out.update(price=None, status=f"error: {exc}")
    except KeyError as exc:
        out.update(price=None, status=f"error: no symbol mapping for {exc}")
    return out


def fetch_all(provider="yahoo", get=http_get_json, instruments=None):
    return {i["name"]: fetch_one(i, provider, get) for i in (instruments or ALL)}


def write_snapshot(results, path):
    doc = dict(fetched_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), quotes=results)
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2)
    return doc


def read_snapshot(path):
    """-> dict or None if the file is missing/unreadable."""
    try:
        with open(path) as fh:
            doc = json.load(fh)
        assert isinstance(doc.get("quotes"), dict)
        return doc
    except (OSError, ValueError, AssertionError):
        return None
