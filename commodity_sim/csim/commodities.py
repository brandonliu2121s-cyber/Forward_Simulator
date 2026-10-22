"""The nine simulated commodities (three each in Agriculture, Energy and Metals) and the personality of each one.

Each profile feeds the price simulator:
  mu        annual drift of the long-run level
  sigma     annual volatility of daily returns
  kappa     speed of reversion to the long-run level (per year; high = snaps back)
  season    (amplitude, peak) seasonal swing as a fraction of price, and the fraction of the year (0..1) at which it peaks
  phi       momentum: how much of yesterday's move carries into today (trending markets)
  garch     (alpha, beta) volatility clustering; calm and stormy spells
  jumps     (events per year, typical size, [(label, direction)]) occasional supply/demand shocks
lot = units per tradeable lot, so a lot is a few thousand dollars of notional at the starting price.
"""

GROUPS = ("Agriculture", "Energy", "Metals")

_AGR_EVENTS = [("Drought warning", 1), ("Frost scare", 1), ("Export ban", 1), ("Bumper harvest forecast", -1), ("Demand slump", -1)]
_ENG_EVENTS = [("Pipeline outage", 1), ("Producer output cut", 1), ("Cold snap", 1), ("Demand slump", -1), ("Inventory glut", -1)]
_MET_EVENTS = [("Central bank buying", 1), ("Mine strike", 1), ("Safe-haven rush", 1), ("Strong dollar", -1), ("Weak factory data", -1)]

COMMODITIES = [
    dict(key="corn", name="Corn", group="Agriculture", unit="bu", lot=1000, start=4.50, mu=0.00, sigma=0.24, kappa=0.9, season=(0.09, 0.45), phi=0.02, garch=(0.07, 0.90), jumps=(3, 0.045, _AGR_EVENTS), volume=120000,
         note="Planting-to-harvest swings: tends to carry a risk premium in early summer and sag into harvest."),
    dict(key="wheat", name="Wheat", group="Agriculture", unit="bu", lot=1000, start=5.80, mu=0.00, sigma=0.28, kappa=0.8, season=(0.07, 0.40), phi=0.03, garch=(0.08, 0.89), jumps=(3, 0.05, _AGR_EVENTS), volume=90000,
         note="Reacts to weather and export news; spikes fade as supply adjusts."),
    dict(key="coffee", name="Coffee", group="Agriculture", unit="lb", lot=2500, start=1.90, mu=0.01, sigma=0.32, kappa=0.6, season=(0.10, 0.50), phi=0.04, garch=(0.08, 0.89), jumps=(3, 0.06, _AGR_EVENTS), volume=40000,
         note="Frost and harvest worries drive sharp but short-lived rallies."),
    dict(key="wti", name="WTI Crude Oil", group="Energy", unit="bbl", lot=100, start=78.0, mu=0.00, sigma=0.36, kappa=1.6, season=(0.03, 0.55), phi=0.00, garch=(0.10, 0.87), jumps=(4, 0.06, _ENG_EVENTS), volume=350000,
         note="Volatile and mean-reverting: shocks tend to fade back toward a cost-of-production level."),
    dict(key="natgas", name="Natural Gas", group="Energy", unit="MMBtu", lot=2500, start=3.20, mu=0.00, sigma=0.55, kappa=2.2, season=(0.14, 0.95), phi=0.00, garch=(0.11, 0.86), jumps=(5, 0.09, _ENG_EVENTS), volume=200000,
         note="The most volatile here. Winter premium, big spikes, and a strong pull back to normal."),
    dict(key="brent", name="Brent Crude Oil", group="Energy", unit="bbl", lot=100, start=82.0, mu=0.00, sigma=0.33, kappa=1.4, season=(0.02, 0.55), phi=0.01, garch=(0.10, 0.87), jumps=(4, 0.055, _ENG_EVENTS), volume=300000,
         note="Like WTI but a little calmer; global supply headlines move it."),
    dict(key="gold", name="Gold", group="Metals", unit="oz", lot=5, start=2300.0, mu=0.03, sigma=0.15, kappa=0.12, season=(0.01, 0.10), phi=0.08, garch=(0.06, 0.92), jumps=(2, 0.025, _MET_EVENTS), volume=150000,
         note="Calm and trending; moves on rates, the dollar and fear."),
    dict(key="copper", name="Copper", group="Metals", unit="lb", lot=1000, start=4.20, mu=0.02, sigma=0.22, kappa=0.25, season=(0.015, 0.30), phi=0.07, garch=(0.07, 0.91), jumps=(3, 0.035, _MET_EVENTS), volume=100000,
         note="A growth barometer: trends with the business cycle."),
    dict(key="silver", name="Silver", group="Metals", unit="oz", lot=100, start=28.0, mu=0.02, sigma=0.30, kappa=0.15, season=(0.015, 0.10), phi=0.07, garch=(0.08, 0.90), jumps=(3, 0.04, _MET_EVENTS), volume=80000,
         note="Gold's jumpier cousin: bigger swings in the same direction."),
]
BY_KEY = {c["key"]: c for c in COMMODITIES}


def get(key):
    try:
        return BY_KEY[key]
    except KeyError:
        raise ValueError(f"Unknown commodity {key!r}.") from None


def public_list():
    """JSON-friendly catalogue for the UI."""
    return [dict(key=c["key"], name=c["name"], group=c["group"], unit=c["unit"], lot=c["lot"], start=c["start"], note=c["note"],
                 notional=round(c["start"] * c["lot"], 2)) for c in COMMODITIES]
