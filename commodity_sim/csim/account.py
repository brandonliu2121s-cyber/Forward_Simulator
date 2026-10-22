"""Paper-trading account. One engine used by hand trading and by the backtester, so both fill orders the same way.

Rules:
  - An order placed at the close of bar t can first fill during bar t+1 (never on the bar it was decided on).
  - market: fills at the next open. stop: becomes a market order once price trades through it (gaps fill at the open).
    limit: fills at its price or better once price trades through it (a favourable gap fills at the open).
  - Costs: a fixed commission per fill, a fee in basis points of notional, and slippage in basis points against you on market and stop fills.
  - Long and short. Gross exposure may not exceed max_leverage x equity: an order that would breach it is rejected.
  - Realised P&L uses the average cost of the open position; the equity curve is cash plus position marked at the close.
"""
from dataclasses import dataclass, field

DEFAULT_COSTS = dict(commission=2.0, fee_bps=1.0, slippage_bps=5.0)
ORDER_TYPES = ("market", "stop", "limit")
MAX_QTY = 100000


def clean_costs(costs):
    c = dict(DEFAULT_COSTS)
    for k in c:
        if costs and k in costs:
            v = float(costs[k])
            if not 0 <= v <= (1000 if k != "commission" else 10000):
                raise ValueError(f"Cost {k} is out of range.")
            c[k] = v
    return c


@dataclass
class Account:
    bars: list
    lot: int
    cash: float = 100000.0
    costs: dict = field(default_factory=lambda: dict(DEFAULT_COSTS))
    max_leverage: float = 3.0

    def __post_init__(self):
        self.start_cash = self.cash
        self.qty = 0                      # signed lots
        self.avg = 0.0                    # average entry price of the open position
        self.realised = 0.0
        self.fees_paid = 0.0
        self.working = []                 # orders waiting to fill
        self.fills = []
        self.rejected = []
        self.equity = []                  # one row per processed bar
        self._next_id = 1

    # ---- orders
    def place(self, side, qty, kind="market", price=None, bar=None, oid=None):
        """Queue an order at the close of `bar`. Returns the order dict, or None if it was rejected (see self.rejected)."""
        qty = int(qty)
        o = dict(id=oid if oid is not None else self._next_id, side=side, qty=qty, type=kind, price=price, bar=bar)
        self._next_id = max(self._next_id, o["id"]) + 1
        if side not in ("buy", "sell") or kind not in ORDER_TYPES or not 1 <= qty <= MAX_QTY:
            return self._reject(o, "Invalid order.")
        if kind != "market" and (price is None or not price > 0):
            return self._reject(o, "Stop and limit orders need a positive price.")
        self.working.append(o)
        return o

    def cancel(self, oid):
        before = len(self.working)
        self.working = [o for o in self.working if o["id"] != oid]
        return len(self.working) < before

    def _reject(self, o, why):
        self.rejected.append(dict(o, reason=why))
        return None

    # ---- bar processing
    def advance(self, t):
        """Process bar t: fill what can fill, then mark to market at the close."""
        o_, h_, l_, c_, _ = self.bars[t]
        for o in list(self.working):
            if o["bar"] is not None and o["bar"] >= t:
                continue                                                   # placed on this or a later bar: not live yet
            px = self._fill_price(o, o_, h_, l_)
            if px is None:
                continue
            self.working.remove(o)
            self._fill(o, px, t)
        eq = self.cash + self.qty * self.lot * c_
        self.equity.append(dict(bar=t, cash=round(self.cash, 2), qty=self.qty, close=c_, equity=round(eq, 2)))

    def _fill_price(self, o, op, hi, lo):
        slip = self.costs["slippage_bps"] / 1e4
        buy = o["side"] == "buy"
        if o["type"] == "market":
            return op * (1 + slip) if buy else op * (1 - slip)
        p = o["price"]
        if o["type"] == "stop":
            if buy and hi >= p:
                return max(op, p) * (1 + slip)
            if not buy and lo <= p:
                return min(op, p) * (1 - slip)
            return None
        if buy and lo <= p:                                                 # limit
            return min(op, p)
        if not buy and hi >= p:
            return max(op, p)
        return None

    def _fill(self, o, px, t):
        signed = o["qty"] if o["side"] == "buy" else -o["qty"]
        notional = px * o["qty"] * self.lot
        close = self.bars[t][3]
        new_qty = self.qty + signed
        equity_now = self.cash + self.qty * self.lot * close
        if abs(new_qty) > abs(self.qty) and abs(new_qty) * self.lot * close > self.max_leverage * max(equity_now, 0):
            self.rejected.append(dict(o, reason=f"Rejected: exposure would exceed {self.max_leverage:g}x your equity.", bar_rejected=t))
            return
        fee = self.costs["commission"] + notional * self.costs["fee_bps"] / 1e4
        realised = 0.0
        if self.qty and (self.qty > 0) != (signed > 0):                      # reducing or flipping: realise on the closed part
            closed = min(abs(signed), abs(self.qty))
            realised = closed * self.lot * (px - self.avg) * (1 if self.qty > 0 else -1)
        if new_qty == 0:
            self.avg = 0.0
        elif self.qty == 0 or (self.qty > 0) != (new_qty > 0):
            self.avg = px                                                    # new position, or flipped through zero
        elif abs(new_qty) > abs(self.qty):                                   # adding: blend the average
            self.avg = (self.avg * abs(self.qty) + px * abs(signed)) / abs(new_qty)
        self.cash += -signed * px * self.lot - fee
        self.qty = new_qty
        self.realised += realised - fee
        self.fees_paid += fee
        self.fills.append(dict(bar=t, id=o["id"], side=o["side"], qty=o["qty"], type=o["type"], price=round(px, 4), fee=round(fee, 2), realised=round(realised - fee, 2), position_after=new_qty))

    # ---- views
    def snapshot(self):
        t = self.equity[-1]["bar"] if self.equity else 0
        close = self.bars[t][3]
        unreal = self.qty * self.lot * (close - self.avg) if self.qty else 0.0
        eq = self.cash + self.qty * self.lot * close
        return dict(bar=t, cash=round(self.cash, 2), qty=self.qty, avg=round(self.avg, 4), close=close, equity=round(eq, 2), unrealised=round(unreal, 2),
                    realised=round(self.realised, 2), fees=round(self.fees_paid, 2), exposure=round(abs(self.qty) * self.lot * close, 2),
                    ret=round(eq / self.start_cash - 1, 6), lot=self.lot)


def run_account(bars, lot, orders, start_bar, up_to, cash=100000.0, costs=None, max_leverage=3.0):
    """Replay a journal of orders deterministically. orders: [{id, bar, side, qty, type, price, cancel_bar}] where `bar` is the bar whose close the
    order was placed at (>= start_bar) and cancel_bar (optional) is the bar at whose close it was cancelled. -> dict for the UI."""
    if not 0 <= start_bar <= up_to < len(bars):
        raise ValueError("Bad range.")
    acct = Account(bars, int(lot), float(cash), clean_costs(costs), float(max_leverage))
    if not 100 <= acct.cash <= 1e9:
        raise ValueError("Starting cash is out of range.")
    pending = sorted((o for o in orders if o.get("bar") is not None), key=lambda o: (o["bar"], o.get("id", 0)))
    if len(pending) > 2000:
        raise ValueError("Too many orders.")
    cancels = {o["id"]: o["cancel_bar"] for o in pending if o.get("cancel_bar") is not None and o.get("id") is not None}
    i = 0
    for t in range(start_bar, up_to + 1):
        for oid, cb in list(cancels.items()):
            if cb < t:
                acct.cancel(oid)
                del cancels[oid]
        acct.advance(t)
        while i < len(pending) and pending[i]["bar"] <= t:
            o = pending[i]
            i += 1
            if o["bar"] < start_bar:
                acct.rejected.append(dict(o, reason="Placed before the market started."))
                continue
            acct.place(o["side"], o["qty"], o.get("type", "market"), o.get("price"), bar=o["bar"], oid=o.get("id"))
    for oid, cb in cancels.items():                                           # a cancel placed at the close of the last processed bar takes effect now
        if cb <= up_to:
            acct.cancel(oid)
    snap = acct.snapshot()
    return dict(account=snap, equity=acct.equity, fills=acct.fills, working=acct.working, rejected=acct.rejected)
