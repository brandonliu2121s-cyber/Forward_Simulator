# Saved runs and price history (Supabase)

The dashboard can store setups in its own Postgres database (Supabase) and a scheduled job can keep a live-price history.
It is optional: with no configuration the dashboard is the same static page as before.

| Piece | Where | What it does |
| --- | --- | --- |
| Schema | `supabase/migrations/0001_init.sql` | `runs` (private per user, row-level security) and `price_snapshots` (public read, service-role write) |
| Browser client | `dashboard/store.js` | magic-link sign-in and saved-runs CRUD over `fetch`, no library |
| Saved runs card | Setup page | email sign-in, Save this setup, Load, Delete (two clicks) |
| Price history | `python/supabase_push.py`, `refresh_live.py --push` | inserts live quotes, duplicates ignored |
| Hosting and jobs | `.github/workflows/pages.yml`, `snapshots.yml` | GitHub Pages deploy, hourly weekday snapshot job |

## Set up (about ten minutes)

1. **Create a project** at supabase.com (free tier is enough) and run the migration: SQL Editor, paste `0001_init.sql`, Run
   (or `supabase db push` with the CLI).
2. **Auth URLs**: Authentication, URL Configuration. Set *Site URL* to your Pages address (`https://<user>.github.io/<repo>/`) and add
   it to *Redirect URLs*. Magic links only work back to an allow-listed address.
3. **Point the dashboard at it**: create `dashboard/config.json` with the project URL and the **publishable** key (Project Settings, API Keys):
   ```json
   { "url": "https://<project-ref>.supabase.co", "key": "sb_publishable_..." }
   ```
   or set the repository *variables* `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`. These two values are public by design; row-level security
   is what protects the data. The build refuses a secret or service-role key.
4. **Publish**: Settings, Pages, Source: *GitHub Actions*. Merge to `main` and the `Deploy dashboard` workflow publishes it.
5. **Price history (optional)**: add the repository *secrets* `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` (service-role key, never commit it).
   The `Store live price snapshots` workflow then runs hourly on weekdays; run it once by hand from the Actions tab to check.
   Locally: `SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python3 python/refresh_live.py --no-rebuild --push`.

## Security model

- The page only ever holds the publishable key and the signed-in user's own token. Every `runs` policy is `owner = auth.uid()`, so one user can
  never read, change or delete another user's rows, even with the key from the page source.
- `price_snapshots` is readable by anyone (public market data) and cannot be written from the browser.
- Saved sessions are re-validated by the same importer as a file upload (`IO.parseImport`) before they are applied, so a tampered row cannot
  inject values outside the allowed ranges.
- Delayed, unofficial prices and a simplified model: educational use only, not for trading decisions.

## Checking it

`python3 -m unittest discover -s tests -t .` runs the store against an in-memory fake of Supabase auth and PostgREST (including a
two-user row-level-security check) and the push job against a fake HTTP post. `node tests/ui_smoke.js` drives the Saved runs card end to end
against a mocked backend. To test the real thing after step 1, sign in as two different emails and confirm each sees only their own runs, and
run Supabase's security advisor (it flags tables without row-level security).

## Resume wording (accurate)

"Added a Postgres persistence layer (Supabase) with row-level security, magic-link auth and a scheduled live-price ingestion job to a client-side
forwards market-making simulator." It is managed Postgres, not a custom API server; a thin Python API over the same database is the natural
next step if you want that on the resume as well.
