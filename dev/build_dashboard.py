"""Builds the Forward Desk dashboard (single self-contained HTML file, no server needed).

    python3 dev/build_dashboard.py                    # writes dashboard/index.html (open it in any browser)
    python3 dev/build_dashboard.py --fragment out.html  # also writes the bare fragment (no <html>/<head>/<body>) for publishing

The page embeds dashboard/engine.js (a port of python/reference_model.py, verified by tests/test_dashboard_engine.py),
dashboard/io.js (CSV/JSON import and export, verified by tests/test_dashboard_io.py)
dashboard/store.js (optional Supabase saved runs, enabled by dashboard/config.json)
and the instrument library from python/instruments.py, so there is one source of truth for the numbers.
"""
import argparse
import base64
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
from instruments import ALL, DEFAULT, GLOBALS, params  # noqa: E402
from reference_model import generate_scenario  # noqa: E402
SEED, N_STEPS = 277, 60


def data_json():
    zs, acts = generate_scenario(SEED, N_STEPS)            # the same scenario the Excel workbook ships with
    insts = []
    for i in ALL:
        p = {k: v for k, v in params(i["name"]).items() if k not in GLOBALS}
        insts.append(dict(name=i["name"], type=i["type"], unit=i["unit"], pnl=i["pnl"], note=i["note"], params=p))
    doc = dict(instruments=insts, globals=dict(GLOBALS), scenario=dict(zs=zs, actions=acts, seed=SEED), default=DEFAULT)
    return json.dumps(doc, separators=(",", ":")).replace("</", "<\\/")


def _jwt_role(token):
    """The `role` claim of a legacy JWT key ('anon' or 'service_role'), or None if it is not a JWT."""
    try:
        part = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))).get("role")
    except (IndexError, ValueError):
        return None


def cloud_config_json():
    """The public Supabase URL and publishable key (safe to ship: row-level security protects the data), or 'null' for a static page.
    Sources, first match wins: SUPABASE_URL + SUPABASE_PUBLISHABLE_KEY env vars, then dashboard/config.json {"url": ..., "key": ...}."""
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_PUBLISHABLE_KEY")
    cfg_file = ROOT / "dashboard" / "config.json"
    if not (url and key) and cfg_file.exists():
        doc = json.loads(cfg_file.read_text())
        url, key = doc.get("url"), doc.get("key")
    if not (url and key):
        return "null"
    if key.startswith("sb_secret_") or _jwt_role(key) == "service_role":
        raise SystemExit("Refusing to embed a secret key in the page: use the publishable (anon) key.")
    return json.dumps({"url": url, "key": key}, separators=(",", ":")).replace("</", "<\\/")


def fragment():
    html = (ROOT / "dashboard" / "template.html").read_text()
    html = html.replace("/*__ENGINE__*/", (ROOT / "dashboard" / "engine.js").read_text())
    html = html.replace("/*__IO__*/", (ROOT / "dashboard" / "io.js").read_text())
    html = html.replace("/*__STORE__*/", (ROOT / "dashboard" / "store.js").read_text())
    html = html.replace("/*__CONFIG__*/null", cloud_config_json())
    assert "/*__DATA__*/" in html
    return html.replace("/*__DATA__*/", data_json())


def standalone(frag):
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">"
            "<style>html{color-scheme:dark;background:#161616}body{margin:0}</style></head><body>\n" + frag + "\n</body></html>\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fragment", help="also write the bare fragment to this path")
    a = ap.parse_args()
    frag = fragment()
    out = ROOT / "dashboard" / "index.html"
    out.write_text(standalone(frag))
    print("wrote", out, f"({out.stat().st_size // 1024} KB)")
    if a.fragment:
        Path(a.fragment).write_text(frag)
        print("wrote", a.fragment)
