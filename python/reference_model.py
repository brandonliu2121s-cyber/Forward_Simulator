"""Pure-Python reference implementation of the Excel simulation logic.

Used (a) to generate a reproducible demo scenario and (b) by verify_workbook.py to cross-check the
numbers LibreOffice/Excel compute from the workbook formulas.
"""
import random

from instruments import DEFAULT, params


def fair_forward(spot, p):
    """F = S x (1 + rate_b x d / basis_b) / (1 + rate_a x d / basis_a)  (IRP for FX, cost-of-carry for commodities)."""
    d = p["tenor_days"]
    return spot * (1 + p["rate_b"] * d / p["basis_b"]) / (1 + p["rate_a"] * d / p["basis_a"])


def generate_scenario(seed, n_steps=60):
    """Market moves in step-vol units (1 decimal) and client actions, with flow clustering so inventory builds."""
    rng = random.Random(seed)
    zs, actions, bias = [], [], 0
    for _ in range(n_steps):
        zs.append(round(rng.gauss(0, 1), 1))
        if rng.random() < 0.15:                     # occasionally flip the dominant client side
            bias = rng.choice([-1, 0, 1])
        if rng.random() < 0.30:
            actions.append("NONE")
        else:
            side = bias if (bias != 0 and rng.random() < 0.65) else rng.choice([-1, 1])
            actions.append("BUY" if side > 0 else "SELL")
    return zs, actions


def simulate(zs, actions, p):
    rows = []
    spot = p["spot_init"]
    fwd_prev = fair_forward(spot, p)
    pos, cum, halted = p["start_pos"], 0.0, 0
    hedge_target = p["hedge_target_pct"] * p["pos_limit"]
    for z, act in zip(zs, actions):
        spot = spot + z * p["step_vol_ticks"] * p["tick"]
        fwd = fair_forward(spot, p)
        skew = -max(-1, min(1, pos / p["pos_limit"])) * p["max_skew_ticks"]
        bid = round(fwd / p["tick"] + skew - p["spread_ticks"] / 2) * p["tick"]
        ask = bid + p["spread_ticks"] * p["tick"]
        fill = 0
        if halted == 0 and act == "BUY":
            fill = -p["clip"]          # client buys from us at our ask -> we go shorter
        elif halted == 0 and act == "SELL":
            fill = p["clip"]
        pos_client = pos + fill
        edge = abs(fill) * ((ask - fwd) if fill < 0 else (fwd - bid)) if fill else 0.0
        mtm = pos * (fwd - fwd_prev)
        cum_pre = cum + mtm + edge
        pos_breach = 1 if abs(pos_client) > p["pos_limit"] else 0
        loss_breach = 1 if (not halted and cum_pre <= -p["loss_limit"]) else 0
        if loss_breach:
            hedge = -pos_client
        elif pos_breach:
            hedge = -(pos_client - (1 if pos_client > 0 else -1) * hedge_target)
        else:
            hedge = 0
        hedge_cost = -abs(hedge) * p["hedge_cost_ticks"] * p["tick"]
        pos_close = pos_client + hedge
        step_pnl = mtm + edge + hedge_cost
        cum += step_pnl
        halted = max(halted, loss_breach) if p["halt_on_loss"] == 1 else 0
        rows.append(dict(spot=spot, fwd=fwd, pos_open=pos, skew=skew, bid=bid, ask=ask, fill=fill,
                         edge=edge, mtm=mtm, pos_breach=pos_breach, loss_breach=loss_breach,
                         hedge=hedge, hedge_cost=hedge_cost, pos_close=pos_close,
                         step_pnl=step_pnl, cum=cum, halted=halted))
        pos, fwd_prev = pos_close, fwd
    return rows


if __name__ == "__main__":
    from instruments import ALL
    p = params(DEFAULT)
    for seed in range(1, 600):
        zs, ac = generate_scenario(seed)
        r = simulate(zs, ac, p)
        ph = sum(x["pos_breach"] and not x["loss_breach"] for x in r)
        lb = [i for i, x in enumerate(r, 1) if x["loss_breach"]]
        if ph >= 2 and lb and 36 <= lb[0] <= 52:
            print(seed, "pos hedges", ph, "loss step", lb, "final cum", round(r[-1]["cum"]))
