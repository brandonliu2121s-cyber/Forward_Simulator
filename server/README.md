# Forward Desk local server (saved runs and price history)

A tiny backend with its own database, running on your own machine. It serves the dashboard and stores your data in one SQLite file.
Python standard library only: nothing to install, no accounts, nothing leaves your computer.

```bash
python3 server/app.py                     # then open http://127.0.0.1:8000/
python3 server/app.py --port 0            # pick any free port
python3 server/app.py --auto-refresh 60   # also store live quotes every hour while it runs
```

Your data lives in `data/forward_desk.db` (ignored by git). Delete the file to start fresh; copy it to back up.

## What you get

| Where | What |
| --- | --- |
| Setup page, **Saved runs** card | name a setup and save it, load it later, delete it (two clicks). Appears only when the page is served by this server; opened as a plain file the dashboard works exactly as before |
| `GET /api/snapshots?instrument=Gold&limit=100` | the live-price history |
| `POST /api/snapshots/refresh` | fetch live quotes now and store them (Yahoo by default; `{"provider": "frankfurter"}` for ECB FX fixings) |
| `python3 python/refresh_live.py --no-rebuild --store` | same fetch from the command line, e.g. from cron |

## API

JSON over HTTP on `127.0.0.1`.

| Method and path | Result |
| --- | --- |
| `GET /api/health` | `{"ok": true, "version": 1, "runs": N}` |
| `GET /api/runs` | `{"runs": [{id, name, instrument, created_at, summary}]}`, newest first |
| `POST /api/runs` | body `{name, instrument, session, summary}` (the dashboard's session JSON) gives `201 {"run": ...}` |
| `GET /api/runs/<id>` | `{"run": {..., "session": {...}}}` |
| `DELETE /api/runs/<id>` | `{"deleted": id}` |

Errors are `{"error": "message"}` with 400 (bad input), 404, 413 (too large), 415 (not JSON) or 403 (foreign Host or Origin).

## Design and safety

- **Schema**: `python/local_db.py`. `runs` keeps the session document as validated JSON plus a small summary; `price_snapshots` has a unique
  `(instrument, ts, source)` so fetching twice never duplicates. Constraints (name and instrument length, JSON validity, positive prices) are
  enforced by the database as well as in Python.
- **Loopback only**: the server refuses to bind to anything but 127.0.0.1 / localhost, because it has no accounts.
- **Browser attacks**: a malicious web page you visit could try to call `localhost`. The server rejects a foreign `Host` header (DNS rebinding),
  a foreign `Origin`, non-JSON POSTs (so plain cross-site form posts fail), and never answers CORS preflights.
- **Loading a run** goes through the same importer as a file upload (`IO.parseImport`), so a tampered database row cannot inject out-of-range values.
- Delayed, unofficial prices and a simplified model: educational use only, not for trading decisions.

## Tests

`python3 -m unittest discover -s tests -t .` runs the database layer, the HTTP server (real sockets, temporary database, fake price feed)
and the JS client. `node tests/ui_smoke.js` starts a real server and drives the Saved runs card in a browser, checking the row in the SQLite file.

## Resume wording (accurate)

"Built a local backend (Python, SQLite) for a forwards market-making simulator: a JSON API for saved simulations and a live-price history,
with input validation, database constraints and protection against cross-site and DNS-rebinding requests; covered by unit tests and a
browser end-to-end test." It is a single-user local server, not a deployed multi-user service.
