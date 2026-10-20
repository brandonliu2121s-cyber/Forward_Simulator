"""SQLite storage for the local Forward Desk server (saved runs and a live-price history).

One file, no server process, Python standard library only. Used by server/app.py and python/refresh_live.py --store.
Educational use only: delayed, unofficial prices and a simplified model; not for trading decisions.
"""
import json
import os
import re
import sqlite3
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(ROOT, "data", "forward_desk.db")
MAX_SESSION_BYTES = 1_000_000
SCHEMA_VERSION = 1

SCHEMA = """
create table if not exists runs (
  id         integer primary key autoincrement,
  created_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  name       text not null check (length(name) between 1 and 80),
  instrument text not null check (length(instrument) between 1 and 80),
  session    text not null check (json_valid(session)),
  summary    text not null default '{}' check (json_valid(summary))
);
create index if not exists runs_newest on runs (created_at desc, id desc);
create table if not exists price_snapshots (
  id         integer primary key autoincrement,
  instrument text not null,
  ts         text not null,
  spot       real not null check (spot > 0),
  source     text not null,
  fetched_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  unique (instrument, ts, source)
);
create index if not exists snapshots_instrument_ts on price_snapshots (instrument, ts desc);
"""


class ValidationError(ValueError):
    """The caller sent something we will not store; the message is safe to show to the user."""


def parse_as_of(text):
    """'2026-10-19 14:30:00' -> '2026-10-19T14:30:00Z'; '2026-10-19 (ECB daily fixing)' -> '2026-10-19T00:00:00Z'; else None."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}:\d{2}))?", str(text or ""))
    return f"{m.group(1)}T{m.group(2) or '00:00:00'}Z" if m else None


def snapshot_rows(quotes):
    """quotes: {instrument: {price, as_of, source, status}} as returned by live_data.fetch_all. Failed or undated quotes are skipped."""
    rows = []
    for name, q in quotes.items():
        ts = parse_as_of(q.get("as_of"))
        if q.get("price") is None or ts is None:
            continue
        rows.append(dict(instrument=name, ts=ts, spot=q["price"], source=q.get("source") or "unknown"))
    return rows


def _text(value, label, limit=80):
    s = str(value if value is not None else "").strip()
    if not s:
        raise ValidationError(f"{label} is required.")
    return s[:limit]


def _obj(value, label):
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be a JSON object.")
    return value


class Database:
    def __init__(self, path=DEFAULT_PATH):
        self.path = path
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._lock = threading.Lock()                 # the HTTP server is threaded; serialise access to the one connection
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("pragma foreign_keys = on")
        if path != ":memory:":
            self._db.execute("pragma journal_mode = wal")
        self._db.executescript(SCHEMA)
        self._db.execute(f"pragma user_version = {SCHEMA_VERSION}")
        self._db.commit()

    def close(self):
        with self._lock:
            self._db.close()

    # ---- runs
    @staticmethod
    def _run(row, with_session=False):
        out = dict(id=row["id"], name=row["name"], instrument=row["instrument"], created_at=row["created_at"], summary=json.loads(row["summary"]))
        if with_session:
            out["session"] = json.loads(row["session"])
        return out

    def list_runs(self, limit=50):
        with self._lock:
            rows = self._db.execute("select * from runs order by created_at desc, id desc limit ?", (max(1, min(int(limit), 200)),)).fetchall()
        return [self._run(r) for r in rows]

    def add_run(self, name, instrument, session, summary=None):
        name, instrument = _text(name, "Name"), _text(instrument, "Instrument")
        session, summary = _obj(session, "session"), _obj(summary if summary is not None else {}, "summary")
        blob = json.dumps(session, separators=(",", ":"))
        if len(blob.encode("utf-8")) > MAX_SESSION_BYTES:
            raise ValidationError("That run is too large to store.")
        with self._lock:
            cur = self._db.execute("insert into runs (name, instrument, session, summary) values (?, ?, ?, ?)",
                                   (name, instrument, blob, json.dumps(summary, separators=(",", ":"))))
            self._db.commit()
            row = self._db.execute("select * from runs where id = ?", (cur.lastrowid,)).fetchone()
        return self._run(row)

    def get_run(self, run_id):
        with self._lock:
            row = self._db.execute("select * from runs where id = ?", (int(run_id),)).fetchone()
        return self._run(row, with_session=True) if row else None

    def delete_run(self, run_id):
        with self._lock:
            cur = self._db.execute("delete from runs where id = ?", (int(run_id),))
            self._db.commit()
        return cur.rowcount > 0

    def count_runs(self):
        with self._lock:
            return self._db.execute("select count(*) from runs").fetchone()[0]

    # ---- price snapshots (duplicates of the same instrument, timestamp and source are ignored)
    def add_snapshots(self, rows):
        """-> number of new rows stored."""
        stored = 0
        with self._lock:
            for r in rows:
                cur = self._db.execute("insert or ignore into price_snapshots (instrument, ts, spot, source) values (?, ?, ?, ?)",
                                       (r["instrument"], r["ts"], float(r["spot"]), r["source"]))
                stored += cur.rowcount
            self._db.commit()
        return stored

    def latest_snapshots(self):
        """-> {instrument: {spot, ts, source, fetched_at}} with the newest quote for each instrument."""
        with self._lock:
            rows = self._db.execute(
                "select instrument, ts, spot, source, fetched_at from ("
                " select *, row_number() over (partition by instrument order by ts desc, id desc) as rn from price_snapshots) where rn = 1").fetchall()
        return {r["instrument"]: dict(spot=r["spot"], ts=r["ts"], source=r["source"], fetched_at=r["fetched_at"]) for r in rows}

    def snapshots(self, instrument=None, limit=500):
        sql, args = "select instrument, ts, spot, source from price_snapshots", []
        if instrument:
            sql += " where instrument = ?"
            args.append(instrument)
        sql += " order by ts desc, id desc limit ?"
        args.append(max(1, min(int(limit), 5000)))
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]
