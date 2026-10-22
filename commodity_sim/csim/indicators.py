"""Technical indicators. Every function is causal: the value at bar t uses only bars 0..t, never later ones
(tests check this by comparing results on a series with its truncated prefix). Warm-up values are None."""
import bisect
import math
import statistics

TRADING_DAYS = 252


def _rolling_mean_std(vals, n):
    """Population mean and standard deviation of each trailing window of n (None until full), via running sums. Values are centred first
    so large prices do not lose precision."""
    m, sd = [None] * len(vals), [None] * len(vals)
    if not vals:
        return m, sd
    c0, s1, s2 = vals[0], 0.0, 0.0
    for i, v in enumerate(vals):
        d = v - c0
        s1, s2 = s1 + d, s2 + d * d
        if i >= n:
            o = vals[i - n] - c0
            s1, s2 = s1 - o, s2 - o * o
        if i >= n - 1:
            mean = s1 / n
            m[i], sd[i] = mean + c0, math.sqrt(max(0.0, s2 / n - mean * mean))
    return m, sd


def sma(vals, n):
    out, s = [None] * len(vals), 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(vals, n):
    out, k = [None] * len(vals), 2.0 / (n + 1)
    for i, v in enumerate(vals):
        if i == n - 1:
            out[i] = sum(vals[:n]) / n
        elif i >= n:
            out[i] = v * k + out[i - 1] * (1 - k)
    return out


def rsi(vals, n=14):
    """Wilder's relative strength index, 0..100."""
    out = [None] * len(vals)
    if len(vals) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = vals[i] - vals[i - 1]
        gains, losses = gains + max(d, 0), losses + max(-d, 0)
    ag, al = gains / n, losses / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(vals)):
        d = vals[i] - vals[i - 1]
        ag, al = (ag * (n - 1) + max(d, 0)) / n, (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def macd(vals, fast=12, slow=26, sig=9):
    ef, es = ema(vals, fast), ema(vals, slow)
    line = [None if (a is None or b is None) else a - b for a, b in zip(ef, es)]
    first = next((i for i, v in enumerate(line) if v is not None), None)
    signal = [None] * len(vals)
    if first is not None:
        part = ema([v for v in line[first:]], sig)
        for i, v in enumerate(part):
            signal[first + i] = v
    hist = [None if (a is None or b is None) else a - b for a, b in zip(line, signal)]
    return line, signal, hist


def bollinger(vals, n=20, k=2.0):
    mid, sd = _rolling_mean_std(vals, n)
    up, lo, pct = [None] * len(vals), [None] * len(vals), [None] * len(vals)
    for i in range(n - 1, len(vals)):
        up[i], lo[i] = mid[i] + k * sd[i], mid[i] - k * sd[i]
        pct[i] = 0.5 if up[i] == lo[i] else (vals[i] - lo[i]) / (up[i] - lo[i])
    return mid, up, lo, pct


def atr(high, low, close, n=14):
    """Average true range (Wilder)."""
    tr = [high[0] - low[0]] + [max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])) for i in range(1, len(close))]
    out = [None] * len(close)
    if len(close) >= n:
        out[n - 1] = sum(tr[:n]) / n
        for i in range(n, len(close)):
            out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def roc(vals, n):
    return [None if i < n else vals[i] / vals[i - n] - 1 for i in range(len(vals))]


def realised_vol(vals, n=20):
    """Annualised volatility of daily log returns over the last n returns."""
    rets = [math.log(vals[i] / vals[i - 1]) for i in range(1, len(vals))]
    _, sd = _rolling_mean_std(rets, n)
    out = [None] * len(vals)
    for i in range(n, len(vals)):
        out[i] = sd[i - 1] * math.sqrt(TRADING_DAYS)
    return out


def zscore(vals, n=120):
    mean, sd = _rolling_mean_std(vals, n)
    return [None if m is None else (0.0 if s < 1e-12 else (v - m) / s) for v, m, s in zip(vals, mean, sd)]


def drawdown(vals):
    peak, out = -math.inf, []
    for v in vals:
        peak = max(peak, v)
        out.append(v / peak - 1)
    return out


def seasonal_tendency(close, t, horizon=21, window=3):
    """What this stretch of the year did in earlier years: the average `horizon`-day return starting at the same point
    of the cycle, one or more 252-bar years ago (a few days either side are averaged). Needs more than a year of history. None otherwise."""
    rets, k = [], 1
    while t - k * TRADING_DAYS - window >= 0:
        for d in range(-window, window + 1):
            s = t - k * TRADING_DAYS + d
            if s + horizon <= t and s >= 0:
                rets.append(close[s + horizon] / close[s] - 1)
        k += 1
    return statistics.fmean(rets) if rets else None


def trailing_median(vals, n=252):
    out, win, order = [None] * len(vals), [], []
    for i, v in enumerate(vals):
        if v is not None:
            bisect.insort(win, v)
            order.append(v)
        if len(order) > n:
            old = order.pop(0)
            win.pop(bisect.bisect_left(win, old))
        if len(win) >= 20:
            out[i] = statistics.median(win)
    return out


def compute(bars):
    """All indicators for a list of [o, h, l, c, v] bars -> dict of equal-length lists."""
    o, h, l, c = ([b[i] for b in bars] for i in range(4))
    macd_line, macd_sig, macd_hist = macd(c)
    bb_mid, bb_up, bb_lo, bb_pct = bollinger(c)
    at = atr(h, l, c)
    vol20 = realised_vol(c)
    return dict(
        close=c, high=h, low=l, open=o,
        sma20=sma(c, 20), sma50=sma(c, 50), sma200=sma(c, 200), ema12=ema(c, 12), ema26=ema(c, 26),
        rsi14=rsi(c, 14), macd=macd_line, macd_signal=macd_sig, macd_hist=macd_hist,
        bb_mid=bb_mid, bb_up=bb_up, bb_low=bb_lo, bb_pct=bb_pct,
        atr14=at, atr_pct=[None if a is None else a / x for a, x in zip(at, c)],
        roc20=roc(c, 20), vol20=vol20, vol_med=trailing_median(vol20), z120=zscore(c, 120), dd=drawdown(c),
        season21=[seasonal_tendency(c, t) for t in range(len(c))],
    )
