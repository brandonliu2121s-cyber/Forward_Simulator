"""SQLite storage for saved scenarios (a market plus the orders you placed) and saved backtests."""
import json
import os
import sqlite3
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(ROOT, "data", "commodity_desk.db")
KINDS = ("trade", "backtest")
MAX_BYTES = 400_000

SCHEMA = """
create table if not exists runs (
  id         integer primary key autoincrement,
  created_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  name       text not null check (length(name) between 1 and 80),
  kind       text not null check (kind in ('trade', 'backtest')),
  commodity  text not null check (length(commodity) between 1 and 40),
  params     text not null check (json_valid(params)),
  summary    text not null default '{}' check (json_valid(summary))
);
create index if not exists runs_newest on runs (created_at desc, id desc);
"""


class ValidationError(ValueError):
    pass


class Database:
    def __init__(self, path=DEFAULT_PATH):
        self.path = path
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        if path != ":memory:":
            self._db.execute("pragma journal_mode = wal")
        self._db.executescript(SCHEMA)
        self._db.commit()

    def close(self):
        with self._lock:
            self._db.close()

    @staticmethod
    def _row(r, with_params=False):
        out = dict(id=r["id"], name=r["name"], kind=r["kind"], commodity=r["commodity"], created_at=r["created_at"], summary=json.loads(r["summary"]))
        if with_params:
            out["params"] = json.loads(r["params"])
        return out

    def add(self, name, kind, commodity, params, summary=None):
        name = str(name or "").strip()[:80]
        if not name:
            raise ValidationError("Name is required.")
        if kind not in KINDS:
            raise ValidationError("kind must be trade or backtest.")
        commodity = str(commodity or "").strip()[:40]
        if not commodity:
            raise ValidationError("Commodity is required.")
        if not isinstance(params, dict) or not isinstance(summary if summary is not None else {}, dict):
            raise ValidationError("params and summary must be JSON objects.")
        p = json.dumps(params, separators=(",", ":"))
        if len(p.encode("utf-8")) > MAX_BYTES:
            raise ValidationError("That run is too large to store.")
        with self._lock:
            cur = self._db.execute("insert into runs (name, kind, commodity, params, summary) values (?, ?, ?, ?, ?)",
                                   (name, kind, commodity, p, json.dumps(summary or {}, separators=(",", ":"))))
            self._db.commit()
            row = self._db.execute("select * from runs where id = ?", (cur.lastrowid,)).fetchone()
        return self._row(row)

    def list(self, limit=50):
        with self._lock:
            rows = self._db.execute("select * from runs order by created_at desc, id desc limit ?", (max(1, min(int(limit), 200)),)).fetchall()
        return [self._row(r) for r in rows]

    def get(self, run_id):
        with self._lock:
            row = self._db.execute("select * from runs where id = ?", (int(run_id),)).fetchone()
        return self._row(row, True) if row else None

    def delete(self, run_id):
        with self._lock:
            cur = self._db.execute("delete from runs where id = ?", (int(run_id),))
            self._db.commit()
        return cur.rowcount > 0
