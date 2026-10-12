"""Pure-Python reference implementation of the Excel simulation logic.

Used (a) to generate a reproducible demo scenario and (b) by verify_workbook.py
to cross-check the numbers LibreOffice/Excel compute from the workbook formulas.
"""
import random

DEFAULTS = dict(
    spot_init=1.2850, base_ir=0.04, quote_ir=0.0055, tenor_days=45,
    base_basis=360, quote_basis=365, tick=0.0001, clip=250_000,
    spread_ticks=5, max_skew_ticks=3, pos_limit=1_000_000, hedge_target=0,
    hedge_cost_ticks=1, loss_limit=1_500, halt_on_loss=1, start_pos=0,
)


def fair_forward(spot, p):
    """Covered interest parity: F = S * (1 + r_quote*d/Bq) / (1 + r_base*d/Bb)."""
    d = p["tenor_days"]
    return spot * (1 + p["quote_ir"] * d / p["quote_basis"]) / (1 + p["base_ir"] * d / p["base_basis"])


def generate_scenario(seed, n_steps=60, shock_sd=3.0):
    """Spot shocks (ticks) and client actions, with some flow clustering so inventory builds."""
    rng = random.Random(seed)
    shocks, actions, bias = [], [], 0
    for _ in range(n_steps):
        shocks.append(int(round(rng.gauss(0, shock_sd))))
        if rng.random() < 0.15:                     # occasionally flip the dominant client side
            bias = rng.choice([-1, 0, 1])
        r = rng.random()
        if r < 0.30:
            actions.append("NONE")
        else:
            side = bias if (bias != 0 and rng.random() < 0.65) else rng.choice([-1, 1])
            actions.append("BUY" if side > 0 else "SELL")
    return shocks, actions


def simulate(shocks, actions, p):
    rows = []
    spot = p["spot_init"]
    fwd_prev = fair_forward(spot, p)
    pos, cum, halted = p["start_pos"], 0.0, 0
    for shock, act in zip(shocks, actions):
        spot = spot + shock * p["tick"]
        fwd = fair_forward(spot, p)
        skew = -max(-1, min(1, pos / p["pos_limit"])) * p["max_skew_ticks"]
        bid = round(fwd / p["tick"] + skew - p["spread_ticks"] / 2) * p["tick"]
        ask = bid + p["spread_ticks"] * p["tick"]
        live = halted == 0
        fill = 0
        if live and act == "BUY":
            fill = -p["clip"]          # client buys USD from us at our ask -> we go shorter
        elif live and act == "SELL":
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
            hedge = -(pos_client - (1 if pos_client > 0 else -1) * p["hedge_target"])
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
    p = DEFAULTS
    print("F0 =", fair_forward(p["spot_init"], p))
    for seed in range(1, 400):
        sh, ac = generate_scenario(seed)
        r = simulate(sh, ac, p)
        ph = sum(x["pos_breach"] and not x["loss_breach"] for x in r)
        lb = [i for i, x in enumerate(r, 1) if x["loss_breach"]]
        if ph >= 3 and lb and 35 <= lb[0] <= 55:
            print(seed, "pos hedges", ph, "loss step", lb, "final cum", round(r[-1]["cum"]), "max|pos|", max(abs(x["pos_close"]) for x in r))
