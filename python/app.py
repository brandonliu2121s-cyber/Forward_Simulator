"""Streamlit front end for the forwards market-making simulator.

Run:  streamlit run app.py
Uses the same model as the CLI (reference_model.py), so results match Excel and the CLI.
"""
import io
from pathlib import Path

import pandas as pd
import streamlit as st

from instruments import ALL, DEFAULT, by_name, params
from reference_model import fair_forward, generate_scenario, simulate

SAMPLE = Path(__file__).parent / "sample_scenario.csv"

st.set_page_config(page_title="Forwards Market-Making Simulator", layout="wide")

# ---------------------------------------------------------------- sidebar inputs
sb = st.sidebar
sb.header("Instrument")
names = [i["name"] for i in ALL]
nm = sb.selectbox("Instrument", names, index=names.index(DEFAULT))
inst, p = by_name(nm), params(nm)
unit, ccy, is_fx = inst["unit"], inst["pnl"], inst["type"] == "FX"
dec = max(0, len(f"{inst['tick']:.10f}".rstrip("0").partition(".")[2]))
k_ = lambda name: f"{nm}|{name}"      # per-instrument widget keys, so switching resets the defaults

st.title(f"{nm} Forwards Market-Making Simulator")
st.caption(f"Quote a {p['tenor_days']}-day {nm} forward, skew with inventory, hedge on limit breaches. "
           f"Position: + = long {unit}. Client BUY lifts our Ask; client SELL hits our Bid. "
           f"Levels and rates are illustrative. {inst['note']}")

sb.header("Market")
p["spot_init"] = sb.number_input(f"Spot ({nm})", value=float(p["spot_init"]), step=float(inst["tick"]),
                                 format=f"%.{dec}f", key=k_("spot"))
a_lbl, b_lbl = (f"{unit} rate (%)", f"{ccy} rate (%)") if is_fx else ("Convenience yield (%)", "Financing + storage (%)")
p["rate_a"] = sb.number_input(a_lbl, value=p["rate_a"] * 100, step=0.05, format="%.3f", key=k_("ra")) / 100
p["rate_b"] = sb.number_input(b_lbl, value=p["rate_b"] * 100, step=0.05, format="%.3f", key=k_("rb")) / 100
p["tenor_days"] = sb.number_input("Tenor (days)", min_value=1, value=int(p["tenor_days"]), step=1, key=k_("tenor"))

sb.header("Quoting")
p["clip"] = sb.number_input(f"Clip size ({unit})", min_value=1, value=int(p["clip"]),
                            step=max(1, int(p["clip"]) // 5), key=k_("clip"))
p["spread_ticks"] = sb.number_input("Spread (ticks)", min_value=0.0, value=float(p["spread_ticks"]), step=1.0, key=k_("spread"))
p["max_skew_ticks"] = sb.number_input("Max skew (ticks)", min_value=0.0, value=float(p["max_skew_ticks"]), step=0.5, key=k_("skew"))

sb.header("Risk")
p["pos_limit"] = sb.number_input(f"Position limit ({unit})", min_value=1, value=int(p["pos_limit"]),
                                 step=max(1, int(p["pos_limit"]) // 20), key=k_("poslim"))
hedge_to = sb.number_input(f"Hedge-to level ({unit})", min_value=0, max_value=int(p["pos_limit"]),
                           value=int(p["hedge_target_pct"] * p["pos_limit"]), step=max(1, int(p["clip"])), key=k_("hedge_to"))
p["hedge_target_pct"] = hedge_to / p["pos_limit"]
p["hedge_cost_ticks"] = sb.number_input("Street half-spread (ticks)", min_value=0.0,
                                        value=float(p["hedge_cost_ticks"]), step=0.5, key=k_("hcost"))
p["loss_limit"] = sb.number_input(f"Loss limit ({ccy})", min_value=0.0, value=float(p["loss_limit"]),
                                  step=max(1.0, float(p["loss_limit"]) / 10), key=k_("loss"))
p["halt_on_loss"] = int(sb.checkbox("Halt quoting after loss-limit breach", value=bool(p["halt_on_loss"]), key=k_("halt")))
p["start_pos"] = sb.number_input(f"Starting position ({unit})", value=int(p["start_pos"]), step=int(p["clip"]), key=k_("startpos"))

sb.header("Scenario")
p["step_vol_ticks"] = sb.number_input("Step volatility (ticks per 1σ move)", min_value=0.1,
                                      value=float(p["step_vol_ticks"]), step=0.5, key=k_("vol"))
mode = sb.radio("Source", ["Random", "Upload CSV"], horizontal=True)
shocks = actions = None
if mode == "Random":
    seed = sb.number_input("Seed", min_value=0, value=277, step=1)
    n_steps = sb.number_input("Steps", min_value=1, max_value=1000, value=60, step=10)
    shocks, actions = generate_scenario(int(seed), int(n_steps))
else:
    up = sb.file_uploader("CSV with columns action and move_sigma (or legacy shock, in ticks)", type="csv")
    if SAMPLE.exists():
        sb.download_button("Download sample", SAMPLE.read_bytes(), file_name="sample_scenario.csv")
    if up is None:
        st.info("Upload a scenario CSV (columns `action` = BUY/SELL/NONE and `move_sigma`, or legacy `shock` in ticks) "
                "or switch to Random in the sidebar.")
        st.stop()
    try:
        df_in = pd.read_csv(up)
        df_in.columns = [c.strip().lower() for c in df_in.columns]
        zc = next((c for c in ("move_sigma", "move", "sigma", "z") if c in df_in.columns), None)
        if zc:
            shocks = df_in[zc].astype(float).tolist()
        else:
            shocks = (df_in["shock"].astype(float) / p["step_vol_ticks"]).tolist()
        actions = df_in["action"].astype(str).str.strip().str.upper().tolist()
        bad = sorted(set(actions) - {"BUY", "SELL", "NONE"})
        if bad:
            raise ValueError(f"invalid action(s) {bad}; use BUY/SELL/NONE")
        if not shocks:
            raise ValueError("file has no rows")
    except (KeyError, ValueError) as e:
        st.error(f"Could not read scenario: {e}. Expected an `action` column and `move_sigma` (or `shock`).")
        st.stop()

# ---------------------------------------------------------------- simulate
rows = simulate(shocks, actions, p)
df = pd.DataFrame(rows)
df.insert(0, "action", actions)
df.insert(0, "step", range(1, len(df) + 1))
df["flag"] = ""
df.loc[df.pos_breach == 1, "flag"] = "POS-HEDGE"
df.loc[df.loss_breach == 1, "flag"] = "LOSS-FLAT"
df.loc[(df.halted == 1) & (df.loss_breach == 0), "flag"] = "HALTED"

f0 = fair_forward(p["spot_init"], p)
loss_steps = df.loc[df.loss_breach == 1, "step"].tolist()
pos_hedges = int(((df.pos_breach == 1) & (df.loss_breach == 0)).sum())

# ---------------------------------------------------------------- KPIs
k = st.columns(6)
k[0].metric(f"Total P&L ({ccy})", f"{df.cum.iloc[-1]:,.0f}")
k[1].metric("Spread capture", f"{df.edge.sum():,.0f}")
k[2].metric("MTM", f"{df.mtm.sum():,.0f}")
k[3].metric("Hedge cost", f"{df.hedge_cost.sum():,.0f}")
k[4].metric("Position hedges", pos_hedges)
k[5].metric("Loss-limit breach", f"step {loss_steps[0]}" if loss_steps else "none")
st.caption(f"Initial fair forward F₀ = {f0:.{dec + 1}f} · {int((df.fill != 0).sum())} client fills · "
           f"max |position| {int(df.pos_close.abs().max()):,} {unit}")

# ---------------------------------------------------------------- charts
idx = df.set_index("step")
c1, c2 = st.columns(2)
with c1:
    st.subheader("Quotes vs fair forward")
    st.line_chart(idx[["bid", "fwd", "ask"]])
with c2:
    st.subheader(f"Cumulative P&L ({ccy})")
    st.line_chart(idx[["cum"]])
c3, c4 = st.columns(2)
with c3:
    st.subheader(f"Closing position ({unit})")
    pos = idx[["pos_close"]].copy()
    pos["+limit"], pos["-limit"] = p["pos_limit"], -p["pos_limit"]
    st.line_chart(pos)
with c4:
    st.subheader(f"P&L attribution per step ({ccy})")
    st.bar_chart(idx[["edge", "mtm", "hedge_cost"]])

# ---------------------------------------------------------------- table + export
st.subheader("Step table")
cols = ["step", "action", "fwd", "bid", "ask", "skew", "fill", "hedge", "pos_close",
        "edge", "mtm", "hedge_cost", "step_pnl", "cum", "flag"]
st.dataframe(df[cols], hide_index=True, width="stretch",
             column_config={c: st.column_config.NumberColumn(format=f"%.{dec}f") for c in ("fwd", "bid", "ask")})

buf = io.StringIO()
df[cols].to_csv(buf, index=False)
st.download_button("Download step table (CSV)", buf.getvalue(), file_name="simulation.csv", mime="text/csv")
