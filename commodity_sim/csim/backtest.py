"""Backtesting: strategies, performance metrics, a many-markets (Monte Carlo) test and a parameter sweep.

A strategy is given only what is known at the close of bar t and returns the side it wants to hold (+1 long, 0 flat, -1 short). The order is
placed at that close and fills at the next open, through the same Account engine used for hand trading. Strategies get precomputed indicator
arrays, which are causal (checked in the tests), so nothing from the future can leak in.
"""
import math
import statistics

from . import analysis, commodities, indicators, simulator
from .account import Account, clean_costs

WARMUP = 300                       # bars of history before the playable window, so 200-day averages and last year's seasons exist
STRATEGIES = {
    "signal": dict(label="Desk signal (the Buy/Sell/Hold score)", params=dict(enter=20, exit=5)),
    "sma_cross": dict(label="Moving-average crossover", params=dict(fast=20, slow=50)),
    "rsi_reversion": dict(label="RSI mean reversion", params=dict(period=14, low=30, high=70)),
    "breakout": dict(label="Channel breakout", params=dict(n=20)),
    "buy_hold": dict(label="Buy and hold", params={}),
}


def _num(params, name, default, lo, hi):
    v = params.get(name, default) if params else default
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number.") from None
    if not lo <= v <= hi:
        raise ValueError(f"{name} must be between {lo:g} and {hi:g}.")
    return v


def make_strategy(name, params, bars, ind, key, allow_short):
    """-> f(t, side) giving the side to hold after the close of bar t. `side` is the side currently held."""
    params = params or {}
    short = -1 if allow_short else 0
    if name == "buy_hold":
        return lambda t, side: 1
    if name == "signal":
        enter, exit_ = _num(params, "enter", 20, 5, 80), _num(params, "exit", 5, 0, 40)
        score = analysis.signal_series(ind, bars, key)

        def f(t, side):
            s = score[t]
            if s is None:
                return 0
            if s >= enter:
                return 1
            if s <= -enter:
                return short
            if side == 1 and s > exit_:
                return 1
            if side == -1 and s < -exit_:
                return -1
            return 0
        return f
    if name == "sma_cross":
        fast, slow = int(_num(params, "fast", 20, 2, 100)), int(_num(params, "slow", 50, 5, 250))
        if fast >= slow:
            raise ValueError("fast must be shorter than slow.")
        a, b = indicators.sma(ind["close"], fast), indicators.sma(ind["close"], slow)
        return lambda t, side: 0 if a[t] is None or b[t] is None else (1 if a[t] > b[t] else short)
    if name == "rsi_reversion":
        period, lo, hi = int(_num(params, "period", 14, 2, 50)), _num(params, "low", 30, 5, 50), _num(params, "high", 70, 50, 95)
        r = indicators.rsi(ind["close"], period)

        def f(t, side):
            v = r[t]
            if v is None:
                return 0
            if v < lo:
                return 1
            if v > hi:
                return short
            if side == 1 and v < 50:
                return 1
            if side == -1 and v > 50:
                return -1
            return 0
        return f
    if name == "breakout":
        n = int(_num(params, "n", 20, 5, 120))
        hi_, lo_ = ind["high"], ind["low"]

        def f(t, side):
            if t < n:
                return 0
            top, bot = max(hi_[t - n:t]), min(lo_[t - n:t])
            exit_n = max(3, n // 2)
            c = ind["close"][t]
            if c > top:
                return 1
            if c < bot:
                return short
            if side == 1 and c > min(lo_[t - exit_n:t]):
                return 1
            if side == -1 and c < max(hi_[t - exit_n:t]):
                return -1
            return 0
        return f
    raise ValueError(f"Unknown strategy {name!r}.")


# ---------------------------------------------------------------- metrics
def round_trips(fills, bars, lot, last_bar):
    """Group fills into trades: from flat to flat (a flip through zero ends one trade and starts the next)."""
    trips, cur, pos = [], None, 0
    for f in fills:
        signed = f["qty"] if f["side"] == "buy" else -f["qty"]
        if cur is None:
            cur = dict(entry_bar=f["bar"], side="long" if signed > 0 else "short", entry_price=f["price"], pnl=0.0, qty=abs(signed), peak=abs(signed))
        cur["pnl"] += f["realised"]
        new = f["position_after"]
        cur["peak"] = max(cur["peak"], abs(new))
        if new == 0 or (pos > 0) != (new > 0) and pos != 0:
            cur.update(exit_bar=f["bar"], exit_price=f["price"], qty=cur["peak"], open=False)
            cur["bars_held"] = cur["exit_bar"] - cur["entry_bar"]
            cur["pnl"] = round(cur["pnl"], 2)
            trips.append(cur)
            cur = None
            if new != 0:                                                     # flipped: the remainder opens the next trade
                cur = dict(entry_bar=f["bar"], side="long" if new > 0 else "short", entry_price=f["price"], pnl=0.0, qty=abs(new), peak=abs(new))
        pos = new
    if cur is not None:
        close = bars[last_bar][3]
        unreal = pos * lot * (close - cur["entry_price"])
        cur.update(exit_bar=last_bar, exit_price=close, qty=cur["peak"], open=True, bars_held=last_bar - cur["entry_bar"], pnl=round(cur["pnl"] + unreal, 2))
        trips.append(cur)
    return trips


def metrics(equity_rows, trips, start_cash):
    eq = [r["equity"] for r in equity_rows]
    n = len(eq)
    out = dict(start=eq[0], end=eq[-1], total_return=eq[-1] / eq[0] - 1)
    years = (n - 1) / simulator.TRADING_DAYS
    out["annualised_return"] = (1 + out["total_return"]) ** (1 / years) - 1 if years > 0 and 1 + out["total_return"] > 0 else None
    rets = [eq[i] / eq[i - 1] - 1 for i in range(1, n)]
    sd = statistics.pstdev(rets) if len(rets) > 1 else 0.0
    out["volatility"] = sd * math.sqrt(simulator.TRADING_DAYS)
    out["sharpe"] = statistics.fmean(rets) / sd * math.sqrt(simulator.TRADING_DAYS) if sd > 1e-12 else None
    peak, worst, run, longest = eq[0], 0.0, 0, 0
    for v in eq:
        peak = max(peak, v)
        dd = v / peak - 1
        worst = min(worst, dd)
        run = run + 1 if v < peak else 0
        longest = max(longest, run)
    out["max_drawdown"], out["longest_drawdown_bars"] = worst, longest
    closed = [t for t in trips if not t["open"]]
    wins, losses = [t["pnl"] for t in closed if t["pnl"] > 0], [t["pnl"] for t in closed if t["pnl"] <= 0]
    out["trades"], out["open_trade"] = len(closed), any(t["open"] for t in trips)
    out["win_rate"] = len(wins) / len(closed) if closed else None
    out["profit_factor"] = sum(wins) / -sum(losses) if losses and sum(losses) < 0 else None
    out["avg_trade"] = statistics.fmean([t["pnl"] for t in closed]) if closed else None
    out["exposure"] = sum(1 for r in equity_rows if r["qty"]) / n
    return out


# ---------------------------------------------------------------- the run
def backtest(bars, ind, key, strategy, params=None, start_bar=WARMUP, end_bar=None, cash=100000.0, costs=None, alloc=0.5, allow_short=False):
    prof = commodities.get(key)
    end_bar = len(bars) - 1 if end_bar is None else end_bar
    if not 0 <= start_bar < end_bar < len(bars):
        raise ValueError("Bad range.")
    if not 0.05 <= alloc <= 2.0:
        raise ValueError("Allocation must be between 5% and 200% of equity.")
    acct = Account(bars, prof["lot"], float(cash), clean_costs(costs))
    fn = make_strategy(strategy, params, bars, ind, key, allow_short)
    side = 0
    for t in range(start_bar, end_bar + 1):
        acct.advance(t)
        if t == end_bar:
            break
        eq = acct.equity[-1]["equity"]
        if eq <= 0:
            break
        cur = (acct.qty > 0) - (acct.qty < 0)
        want = fn(t, cur)
        if want != cur:                                                      # size only when the side changes: no daily rebalancing
            want_qty = want * max(1, int(alloc * eq / (bars[t][3] * prof["lot"]))) if want else 0
            delta = want_qty - acct.qty
            if delta:
                acct.place("buy" if delta > 0 else "sell", abs(delta), "market", bar=t)
    trips = round_trips(acct.fills, bars, prof["lot"], acct.equity[-1]["bar"])
    return dict(metrics=metrics(acct.equity, trips, float(cash)), equity=[[r["bar"], r["equity"]] for r in acct.equity], trades=trips, fills=acct.fills,
                rejected=acct.rejected, strategy=strategy, params=params or {})


def compare(bars, ind, key, strategy, params, start_bar, end_bar, cash, costs, alloc, allow_short):
    """The strategy and buy-and-hold on the same market, with the drawdown curve for the strategy."""
    res = backtest(bars, ind, key, strategy, params, start_bar, end_bar, cash, costs, alloc, allow_short)
    bh = backtest(bars, ind, key, "buy_hold", {}, start_bar, end_bar, cash, costs, alloc, False)
    peak, dd = -math.inf, []
    for bar, v in res["equity"]:
        peak = max(peak, v)
        dd.append([bar, round(v / peak - 1, 5)])
    res["buy_hold"] = dict(metrics=bh["metrics"], equity=bh["equity"])
    res["drawdown"] = dd
    return res


# ---------------------------------------------------------------- many markets
def monte_carlo(key, strategy, params, n=100, days=250, seed0=1, cash=100000.0, costs=None, alloc=0.5, allow_short=False):
    """Run the same strategy on n different simulated markets. Shows the spread of outcomes: how much is luck, how much is edge."""
    if not 5 <= n <= 300 or not 60 <= days <= 750:
        raise ValueError("Use 5 to 300 markets of 60 to 750 days.")
    rows = []
    for s in range(seed0, seed0 + n):
        m = simulator.simulate(key, s, WARMUP + days)
        ind = indicators.compute(m["bars"])
        r = backtest(m["bars"], ind, key, strategy, params, WARMUP, WARMUP + days - 1, cash, costs, alloc, allow_short)
        b = backtest(m["bars"], ind, key, "buy_hold", {}, WARMUP, WARMUP + days - 1, cash, costs, alloc, False)
        rows.append(dict(seed=s, ret=r["metrics"]["total_return"], bh=b["metrics"]["total_return"], dd=r["metrics"]["max_drawdown"], trades=r["metrics"]["trades"]))
    rets, bh = sorted(x["ret"] for x in rows), [x["bh"] for x in rows]
    q = lambda xs, p: xs[min(len(xs) - 1, max(0, int(round(p * (len(xs) - 1)))))]  # noqa: E731
    lo, hi = rets[0], rets[-1]
    k = 20
    width = (hi - lo) / k if hi > lo else 1.0
    hist = [0] * k
    for v in rets:
        hist[min(k - 1, int((v - lo) / width))] += 1
    diff = [x["ret"] - x["bh"] for x in rows]
    return dict(n=n, days=days, summary=dict(mean=statistics.fmean(rets), median=q(rets, 0.5), p5=q(rets, 0.05), p25=q(rets, 0.25), p75=q(rets, 0.75), p95=q(rets, 0.95),
                                             profitable=sum(1 for v in rets if v > 0) / n, beat_buy_hold=sum(1 for d in diff if d > 0) / n, mean_vs_buy_hold=statistics.fmean(diff),
                                             buy_hold_mean=statistics.fmean(bh), median_max_drawdown=statistics.median(x["dd"] for x in rows), mean_trades=statistics.fmean(x["trades"] for x in rows)),
                histogram=dict(lo=lo, width=width, counts=hist), runs=rows[:300])


# ---------------------------------------------------------------- parameter sweep
def sweep_sma(bars, ind, key, start_bar, end_bar, cash, costs, alloc, allow_short, fasts=(5, 10, 20), slows=(30, 50, 100, 200)):
    """Try moving-average crossovers on the first half of the window ("train") and report how each did on the second half ("test").
    The best in-sample setting usually does worse out of sample: that gap is overfitting."""
    mid = start_bar + (end_bar - start_bar) // 2
    rows = []
    for f in fasts:
        for s in slows:
            if f >= s:
                continue
            r = backtest(bars, ind, key, "sma_cross", dict(fast=f, slow=s), start_bar, end_bar, cash, costs, alloc, allow_short)
            eq = {b: v for b, v in r["equity"]}
            a, m, z = eq[start_bar], eq[mid], eq[end_bar]
            rows.append(dict(fast=f, slow=s, train=m / a - 1, test=z / m - 1, total=z / a - 1, trades=r["metrics"]["trades"]))
    rows.sort(key=lambda x: -x["train"])
    for i, x in enumerate(rows):
        x["rank_train"] = i + 1
    best = rows[0] if rows else None
    return dict(rows=rows, split_bar=mid, best_train=best, note=("The best setting on the first half returned %+.1f%% there and %+.1f%% on the second half." % (best["train"] * 100, best["test"] * 100)) if best else "")
