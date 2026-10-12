"""Instrument library for the forwards market-making simulator.

All market levels / rates are ILLUSTRATIVE placeholders, not live data. Overwrite them in the
workbook's Instruments sheet (or here) before drawing conclusions.

Pricing convention (one formula for every instrument):
    F = S x (1 + rate_b x d / basis_b) / (1 + rate_a x d / basis_a)
  FX pair  BASE/QUOTE : rate_a = BASE-ccy rate, rate_b = QUOTE-ccy rate   (covered interest parity)
  Commodity           : rate_a = convenience yield, rate_b = financing + storage cost (cost of carry)
"""


def _fx(name, base, quote, spot, ra, rb, ba, bb, tick, clip, spread, skew, step_vol, note,
        tenor=45, pos_limit=1_000_000, hedge_cost=1.0):
    return dict(name=name, type="FX", unit=base, pnl=quote, spot=spot, rate_a=ra, financing=None, storage=None,
                rate_b=rb, basis_a=ba, basis_b=bb, tenor_days=tenor, tick=tick, clip=clip, spread_ticks=spread,
                max_skew_ticks=skew, pos_limit=pos_limit, hedge_cost_ticks=hedge_cost, step_vol_ticks=step_vol,
                loss_limit=round(6 * pos_limit * step_vol * tick), note=note)


def _cmd(name, unit, spot, cy, fin, sto, tick, clip, spread, skew, pos_limit, step_vol, note,
         tenor=90, hedge_cost=1.0):
    return dict(name=name, type="Commodity", unit=unit, pnl="USD", spot=spot, rate_a=cy, financing=fin,
                storage=sto, rate_b=fin + sto, basis_a=365, basis_b=365, tenor_days=tenor, tick=tick, clip=clip,
                spread_ticks=spread, max_skew_ticks=skew, pos_limit=pos_limit, hedge_cost_ticks=hedge_cost,
                step_vol_ticks=step_vol, loss_limit=round(6 * pos_limit * step_vol * tick), note=note)


INSTRUMENTS = [
    _fx("USD/SGD", "USD", "SGD", 1.2850, 0.0400, 0.0055, 360, 365, 0.0001, 250_000, 5, 3, 3,
        "Original project brief: USD 4.00%, SGD 0.55%, 45-day tenor, USD 250k, 5-tick spread. Spot illustrative."),
    _fx("EUR/USD", "EUR", "USD", 1.1600, 0.0200, 0.0400, 360, 360, 0.0001, 250_000, 2, 1, 4,
        "Most liquid pair: tight spread. Rates illustrative (EUR 2.00%, USD 4.00%).", hedge_cost=0.5),
    _fx("GBP/USD", "GBP", "USD", 1.3400, 0.0400, 0.0400, 365, 360, 0.0001, 250_000, 3, 2, 5,
        "Rates illustrative (GBP 4.00%, USD 4.00%): near-zero carry, forward ~ spot."),
    _fx("USD/JPY", "USD", "JPY", 150.00, 0.0400, 0.0050, 360, 360, 0.01, 250_000, 3, 2, 6,
        "JPY quoted to 2 decimals (1 tick = 0.01). Large forward discount: USD yield >> JPY yield. Illustrative."),
    _fx("AUD/USD", "AUD", "USD", 0.6600, 0.0360, 0.0400, 365, 360, 0.0001, 250_000, 3, 2, 4,
        "Rates illustrative (AUD 3.60%, USD 4.00%)."),
    _fx("USD/CHF", "USD", "CHF", 0.8000, 0.0400, 0.0025, 360, 360, 0.0001, 250_000, 3, 2, 4,
        "Rates illustrative (USD 4.00%, CHF 0.25%): large forward discount."),
    _fx("USD/CNH", "USD", "CNH", 7.1500, 0.0400, 0.0180, 360, 365, 0.0001, 250_000, 8, 4, 5,
        "Offshore yuan: wider spread / skew than G10. Rates illustrative (USD 4.00%, CNH 1.80%)."),
    _cmd("Gold", "oz", 4000.00, 0.0020, 0.0400, 0.0010, 0.10, 1_000, 5, 3, 4_000, 15,
         "Price USD/oz, 90-day forward. Conv. yield ~ lease rate 0.20%; financing 4.00% + storage 0.10%. Contango. Illustrative."),
    _cmd("Silver", "oz", 45.00, 0.0030, 0.0400, 0.0030, 0.01, 50_000, 5, 3, 200_000, 10,
         "Price USD/oz, 90-day forward. Conv. yield 0.30%; financing 4.00% + storage 0.30%. Illustrative."),
    _cmd("WTI Crude", "bbl", 65.00, 0.0700, 0.0400, 0.0200, 0.01, 10_000, 4, 3, 40_000, 8,
         "Price USD/bbl, 90-day forward. Conv. yield 7.00% > carry 6.00% -> mild BACKWARDATION (forward < spot). Illustrative."),
    _cmd("Copper", "t", 10000.00, 0.0200, 0.0400, 0.0100, 0.50, 25, 4, 2, 100, 10,
         "Price USD/tonne, 90-day forward. Conv. yield 2.00%; financing 4.00% + storage 1.00%. Illustrative."),
    _cmd("Natural Gas", "MMBtu", 3.50, 0.0000, 0.0400, 0.1200, 0.001, 10_000, 5, 3, 40_000, 10,
         "Price USD/MMBtu, 90-day forward. Very high storage cost (12%) -> steep CONTANGO. Illustrative."),
]
CUSTOM = _fx("Custom (edit me)", "USD", "MYR", 4.2000, 0.0400, 0.0300, 360, 365, 0.0001, 250_000, 8, 4, 5,
             "EXAMPLE ROW (USD/MYR, illustrative): overwrite every blue cell with your own instrument.")
ALL = INSTRUMENTS + [CUSTOM]
DEFAULT = "USD/SGD"


def by_name(nm):
    return next(i for i in ALL if i["name"] == nm)


GLOBALS = dict(hedge_target_pct=0.0, halt_on_loss=1, start_pos=0)


def params(nm):
    """Model parameter dict for the reference model, for instrument `nm`."""
    i = by_name(nm)
    keys = ("spot rate_a rate_b basis_a basis_b tenor_days tick clip spread_ticks max_skew_ticks pos_limit "
            "loss_limit hedge_cost_ticks step_vol_ticks").split()
    p = {k: i[k] for k in keys}
    p["spot_init"] = p.pop("spot")
    p.update(GLOBALS)
    return p
