"""Seeded commodity price simulator.

The same (commodity, seed, length) always gives the same market. Prices are built from:
  - a slowly drifting long-run level the price is pulled back toward (strong for energy, weak for metals),
  - a seasonal swing (strong for agriculture and natural gas),
  - momentum (metals trend),
  - volatility that clusters (GARCH(1,1)): calm spells and stormy spells,
  - occasional labelled supply/demand shocks.
Daily bars come out as open/high/low/close/volume on a business-day calendar.
This is a teaching model, not a forecast of anything real.
"""
import datetime
import math
import random

from . import commodities

TRADING_DAYS = 252
START_DATE = datetime.date(2023, 1, 2)
MAX_BARS = 2500


def business_dates(n, start=START_DATE):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += datetime.timedelta(days=1)
    return out


def simulate(key, seed, n_bars):
    """-> dict(bars=[[o,h,l,c,v], ...], events=[{bar, label, pct}], dates=[...], commodity=profile name). Deterministic."""
    p = commodities.get(key)
    if not 2 <= int(n_bars) <= MAX_BARS:
        raise ValueError(f"Length must be between 2 and {MAX_BARS} bars.")
    n_bars = int(n_bars)
    rng = random.Random(f"{int(seed)}:{key}")
    amp, peak = p["season"]
    phase = peak - 0.25                                       # sin() peaks a quarter cycle after its phase
    a, b = p["garch"]
    h0 = p["sigma"] ** 2 / TRADING_DAYS
    omega = (1 - a - b) * h0
    lam, jsize, ev = p["jumps"]
    s_off = amp * math.sin(2 * math.pi * (0 - phase))        # so the first close equals the starting price exactly
    s0 = 0.0
    level0 = math.log(p["start"])
    y_prev = level0                                            # de-seasonalised log price
    x_prev, s_prev, dy_prev, h, e_prev = y_prev + s0, s0, 0.0, h0, 0.0
    close_prev = math.exp(x_prev)
    bars, events = [], []
    for t in range(n_bars):
        s = amp * math.sin(2 * math.pi * (t / TRADING_DAYS - phase)) - s_off
        level_prev, level = level0 + p["mu"] * max(t - 1, 0) / TRADING_DAYS, level0 + p["mu"] * t / TRADING_DAYS
        h = omega + a * e_prev ** 2 + b * h if t else h0
        z = rng.gauss(0, 1)
        e = math.sqrt(h) * z
        jump = 0.0
        if rng.random() < lam / TRADING_DAYS:
            label, direction = ev[rng.randrange(len(ev))]
            jump = direction * abs(rng.gauss(jsize, jsize / 3))
            events.append(dict(bar=t, label=label, pct=round((math.exp(jump) - 1) * 100, 1)))
        dy = (level - level_prev) + p["kappa"] / TRADING_DAYS * (level_prev - y_prev) + p["phi"] * dy_prev + e + jump
        y = y_prev + dy
        x = y + s
        close = math.exp(x) if t else math.exp(x_prev)
        r = math.log(close / close_prev) if t else 0.0
        sd = math.sqrt(h)
        gap = 0.3 * r + 0.3 * sd * rng.gauss(0, 1)
        o = close_prev * math.exp(gap) if t else close
        hi = max(o, close) * math.exp(abs(rng.gauss(0, 1)) * 0.5 * sd)
        lo = min(o, close) * math.exp(-abs(rng.gauss(0, 1)) * 0.5 * sd)
        vol = int(p["volume"] * math.exp(0.3 * rng.gauss(0, 1)) * (1 + 3 * min(abs(e) / math.sqrt(h0), 4) / 4 + 2 * abs(jump) / max(jsize, 1e-9) / 4))
        decimals = 4 if close < 20 else 2
        bars.append([round(o, decimals), round(hi, decimals), round(lo, decimals), round(close, decimals), vol])
        y_prev, dy_prev, e_prev, close_prev = y, dy, e, close
    # rounding can nudge a bar's extremes inside its open/close: repair so every bar is internally consistent
    for bar in bars:
        bar[1], bar[2] = max(bar[0], bar[1], bar[3]), min(bar[0], bar[2], bar[3])
    return dict(bars=bars, events=events, dates=business_dates(n_bars), commodity=p["name"])
