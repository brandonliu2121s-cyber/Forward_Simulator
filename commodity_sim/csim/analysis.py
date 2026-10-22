"""Analysis and Buy / Sell / Hold signals.

Five kinds of evidence each cast a vote between -1 (bearish) and +1 (bullish), with a plain-English reason:
  trend, momentum, mean reversion, seasonality (and volatility, which does not vote but lowers confidence).
The votes are weighted by what each commodity group tends to respond to in this simulator, summed to a score from -100 to +100,
and mapped to Buy (>= +20), Sell (<= -20) or Hold. Only data up to bar t is used.

Because the simulator is built with these very patterns (energy snaps back, metals trend, agriculture has seasons), the signals can
look sensible here. That says nothing about real markets, where the patterns are weaker, change, and are widely traded.
"""
import math

from . import commodities

WEIGHTS = {   # trend, momentum, mean reversion, seasonality (each row sums to 1)
    "Agriculture": dict(trend=0.20, momentum=0.10, reversion=0.35, season=0.35),
    "Energy": dict(trend=0.15, momentum=0.10, reversion=0.55, season=0.20),
    "Metals": dict(trend=0.45, momentum=0.30, reversion=0.15, season=0.10),
}
BUY_AT, SELL_AT = 20.0, -20.0
MIN_BARS = 60
LABEL = {"trend": "Trend", "momentum": "Momentum", "reversion": "Mean reversion", "season": "Seasonality"}


def _clamp(x, lim=1.0):
    return max(-lim, min(lim, x))


def _tanh(x):
    return math.tanh(x)


def vote_trend(ind, t):
    c, s50, s200, hist, hist_prev, ap = ind["close"][t], ind["sma50"][t], ind["sma200"][t], ind["macd_hist"][t], ind["macd_hist"][t - 1], ind["atr_pct"][t]
    if None in (s50, hist, hist_prev, ap) or ap <= 0:
        return 0.0, "Not enough history for a trend read yet."
    slow, slow_name = (s200, "200-day") if s200 is not None else (ind["sma20"][t], "20-day")
    a = _tanh((c / s50 - 1) / (1.5 * ap))
    b = _tanh((s50 / slow - 1) / (3 * ap))
    m = _clamp(hist / (0.5 * ap * c) * 4) if hist else 0.0
    v = (a + b + m) / 3
    side = "above" if c > s50 else "below"
    cross = "above" if s50 > slow else "below"
    return v, f"Price is {abs(c / s50 - 1) * 100:.1f}% {side} its 50-day average, which is {cross} the {slow_name} average; MACD momentum is {'rising' if hist > hist_prev else 'fading'}."


def vote_momentum(ind, t):
    r, vol = ind["roc20"][t], ind["vol20"][t]
    if r is None or vol is None or vol <= 0:
        return 0.0, "Not enough history for a momentum read yet."
    z = r / (vol * math.sqrt(20 / 252))
    return _tanh(0.7 * z), f"Price moved {r * 100:+.1f}% over 20 days, about {abs(z):.1f} typical moves {'up' if r > 0 else 'down'}."


def vote_reversion(ind, t):
    z, rsi = ind["z120"][t], ind["rsi14"][t]
    if z is None or rsi is None:
        return 0.0, "Not enough history to judge how stretched the price is."
    r = 0.0
    if rsi > 70:
        r = -min(1.0, (rsi - 70) / 15)
    elif rsi < 30:
        r = min(1.0, (30 - rsi) / 15)
    v = 0.6 * (-_tanh(0.8 * z)) + 0.4 * r
    where = "above" if z > 0 else "below"
    note = " RSI is overbought." if rsi > 70 else " RSI is oversold." if rsi < 30 else ""
    return v, f"Price is {abs(z):.1f} standard deviations {where} its 6-month average (RSI {rsi:.0f}); stretched prices tend to snap back.{note}"


def vote_season(ind, t):
    tend, vol = ind["season21"][t], ind["vol20"][t]
    if tend is None or vol is None or vol <= 0:
        return 0.0, "Seasonality needs more than a year of history."
    z = tend / (vol * math.sqrt(21 / 252))
    return _tanh(1.0 * z), f"At this point of the year the price has typically moved {tend * 100:+.1f}% over the next month in earlier years."


def volatility_state(ind, t):
    vol, med = ind["vol20"][t], ind["vol_med"][t]
    if vol is None or med is None or med <= 0:
        return 1.0, "normal"
    ratio = vol / med
    return ratio, "high" if ratio > 1.5 else "low" if ratio < 0.7 else "normal"


def analyze(ind, bars, t, key):
    """Everything the UI shows for day t of commodity `key`. `ind` is indicators.compute(bars) (causal, so safe to reuse)."""
    prof = commodities.get(key)
    close = ind["close"][t]
    out = dict(bar=t, close=close, signal="Hold", score=0.0, confidence="Low", votes=[], summary="", change_mind="", levels={}, sizing={}, volatility={})
    if t < MIN_BARS:
        out["summary"] = f"{prof['name']}: only {t + 1} days of history so far; the signal needs about {MIN_BARS}."
        return out
    w = WEIGHTS[prof["group"]]
    votes = []
    for name, fn in (("trend", vote_trend), ("momentum", vote_momentum), ("reversion", vote_reversion), ("season", vote_season)):
        v, reason = fn(ind, t)
        votes.append(dict(name=name, label=LABEL[name], vote=round(v, 3), weight=w[name], contribution=round(100 * w[name] * v, 1), reason=reason))
    score = sum(100 * x["weight"] * x["vote"] for x in votes)
    ratio, regime = volatility_state(ind, t)
    signal = "Buy" if score >= BUY_AT else "Sell" if score <= SELL_AT else "Hold"
    sign = 1 if score > 0 else -1
    agree = sum(x["weight"] for x in votes if x["vote"] * sign > 0.05) / sum(x["weight"] for x in votes)
    conf = min(1.0, abs(score) / 60) * (0.5 + 0.5 * agree) * (0.75 if regime == "high" else 1.0)
    if signal == "Hold":
        conf = 1 - min(1.0, abs(score) / 20) * 0.7                                  # a hold is confident when the evidence is near zero
    confidence = "High" if conf >= 0.6 else "Medium" if conf >= 0.35 else "Low"
    atr = ind["atr14"][t]
    lo20, hi20 = min(ind["low"][t - 19:t + 1]), max(ind["high"][t - 19:t + 1])
    levels = dict(support=round(lo20, 4), resistance=round(hi20, 4))
    if atr:
        levels["stop"] = round(close - 2 * atr, 4) if signal != "Sell" else round(close + 2 * atr, 4)
        levels["target"] = round(close + 3 * atr, 4) if signal != "Sell" else round(close - 3 * atr, 4)
        risk_per_lot = 2 * atr * prof["lot"]
        out["sizing"] = dict(lot=prof["lot"], notional=round(close * prof["lot"], 2), atr=round(atr, 4), risk_per_lot=round(risk_per_lot, 2))
    ranked = sorted(votes, key=lambda x: -abs(x["contribution"]))
    lead = [x for x in ranked if abs(x["contribution"]) >= 1.5][:2]
    why = " ".join(x["reason"] for x in lead) or "No single piece of evidence stands out."
    stance = {"Buy": "leans bullish", "Sell": "leans bearish", "Hold": "is balanced"}[signal]
    extra = {"high": " Volatility is running high, so expect bigger swings and size down.", "low": " Volatility is unusually low; quiet markets can break out.", "normal": ""}[regime]
    out.update(signal=signal, score=round(score, 1), confidence=confidence, votes=votes, levels=levels,
               volatility=dict(ratio=round(ratio, 2), regime=regime), agreement=round(agree, 2),
               summary=f"{prof['name']} {stance} (score {score:+.0f} of 100). {why}{extra}",
               change_mind=_change_mind(signal, ind, t, ranked))
    return out


def _change_mind(signal, ind, t, ranked):
    c, s50, rsi = ind["close"][t], ind["sma50"][t], ind["rsi14"][t]
    if signal == "Buy":
        bits = []
        if s50 is not None and c > s50:
            bits.append(f"a close below the 50-day average ({s50:.2f})")
        if rsi is not None:
            bits.append(f"RSI climbing above 70 (now {rsi:.0f})")
        return "This view weakens on " + " or ".join(bits or ["a sharp fall"]) + "."
    if signal == "Sell":
        bits = []
        if s50 is not None and c < s50:
            bits.append(f"a close above the 50-day average ({s50:.2f})")
        if rsi is not None:
            bits.append(f"RSI falling below 30 (now {rsi:.0f})")
        return "This view weakens on " + " or ".join(bits or ["a sharp rise"]) + "."
    top = ranked[0]
    return f"A clearer call would need the evidence to line up; the biggest swing factor right now is {top['label'].lower()}."


def signal_series(ind, bars, key):
    """Score and Buy/Sell/Hold for every bar (None before MIN_BARS). Reuses the same rules, so what the chart marks is what the panel says."""
    out = []
    prof = commodities.get(key)
    w = WEIGHTS[prof["group"]]
    for t in range(len(bars)):
        if t < MIN_BARS:
            out.append(None)
            continue
        s = 0.0
        for name, fn in (("trend", vote_trend), ("momentum", vote_momentum), ("reversion", vote_reversion), ("season", vote_season)):
            s += 100 * w[name] * fn(ind, t)[0]
        out.append(round(s, 1))
    return out


def label_for(score):
    return None if score is None else "Buy" if score >= BUY_AT else "Sell" if score <= SELL_AT else "Hold"
