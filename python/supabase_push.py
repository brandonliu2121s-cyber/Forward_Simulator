"""Push live-price snapshots into the Supabase `price_snapshots` table (see supabase/migrations/0001_init.sql).

Configuration comes from the environment, never from the repo:
    SUPABASE_URL           https://<project>.supabase.co
    SUPABASE_SERVICE_KEY   the service-role key (bypasses row-level security; keep it secret, e.g. a CI secret)

Duplicate (instrument, ts, source) rows are ignored, so re-running the job is harmless.
Educational use only: delayed, unofficial data; not for trading decisions.
"""
import json
import os
import re
import urllib.error
import urllib.request

TABLE = "price_snapshots"


class PushError(Exception):
    pass


def parse_as_of(text):
    """'2026-10-19 14:30:00' -> '2026-10-19T14:30:00Z'; '2026-10-19 (ECB daily fixing)' -> '2026-10-19T00:00:00Z'; else None."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}:\d{2}))?", str(text or ""))
    return f"{m.group(1)}T{m.group(2) or '00:00:00'}Z" if m else None


def rows_from_quotes(quotes):
    """quotes: {instrument: {price, as_of, source, status}} as returned by live_data.fetch_all. Failed quotes are skipped."""
    rows = []
    for name, q in quotes.items():
        ts = parse_as_of(q.get("as_of"))
        if q.get("price") is None or ts is None:
            continue
        rows.append(dict(instrument=name, ts=ts, spot=q["price"], source=q.get("source") or "unknown"))
    return rows


def http_post(url, headers, body, timeout=20):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise PushError(f"Supabase answered {exc.code}: {detail}") from exc
    except Exception as exc:
        raise PushError(f"{type(exc).__name__}: {exc}") from exc


def push(quotes, url=None, key=None, post=http_post):
    """-> number of rows sent. Raises PushError on misconfiguration or HTTP failure."""
    url = (url or os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = key or os.environ.get("SUPABASE_SERVICE_KEY") or ""
    if not url or not key:
        raise PushError("Set SUPABASE_URL and SUPABASE_SERVICE_KEY to push snapshots.")
    if not re.match(r"^https://[a-z0-9-]+\.supabase\.(co|in)$", url) and not re.match(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$", url):
        raise PushError("SUPABASE_URL does not look like a Supabase project URL.")
    rows = rows_from_quotes(quotes)
    if not rows:
        return 0
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "Prefer": "resolution=ignore-duplicates,return=minimal"}
    post(f"{url}/rest/v1/{TABLE}?on_conflict=instrument,ts,source", headers, rows)
    return len(rows)
