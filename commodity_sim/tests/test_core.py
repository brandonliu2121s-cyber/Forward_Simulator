"""Simulator and indicators: determinism, internal consistency, statistical sanity per commodity group, hand-computed indicator values,
and the no-look-ahead property (an indicator at bar t is unchanged when later bars are removed)."""
import math
import os
import statistics
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from csim import commodities, indicators as I, simulator  # noqa: E402


class Catalogue(unittest.TestCase):
    def test_nine_commodities_three_per_group(self):
        self.assertEqual(len(commodities.COMMODITIES), 9)
        for g in commodities.GROUPS:
            self.assertEqual(sum(1 for c in commodities.COMMODITIES if c["group"] == g), 3, g)
        self.assertEqual(len({c["key"] for c in commodities.COMMODITIES}), 9)

    def test_a_lot_is_a_sensible_amount_of_money(self):
        for c in commodities.COMMODITIES:
            self.assertTrue(1000 <= c["start"] * c["lot"] <= 20000, c["key"])

    def test_unknown_commodity(self):
        with self.assertRaises(ValueError):
            commodities.get("unobtainium")


class Simulator(unittest.TestCase):
    def test_deterministic_and_seed_sensitive(self):
        a, b, c = simulator.simulate("wti", 7, 300), simulator.simulate("wti", 7, 300), simulator.simulate("wti", 8, 300)
        self.assertEqual(a, b)
        self.assertNotEqual(a["bars"], c["bars"])
        self.assertNotEqual(simulator.simulate("gold", 7, 300)["bars"], a["bars"])      # same seed, different commodity

    def test_prefix_property_longer_market_extends_the_shorter_one(self):
        short, long = simulator.simulate("corn", 3, 200), simulator.simulate("corn", 3, 400)
        self.assertEqual(short["bars"], long["bars"][:200])

    def test_first_close_is_the_start_price_and_bars_are_consistent(self):
        for c in commodities.COMMODITIES:
            m = simulator.simulate(c["key"], 11, 600)
            self.assertAlmostEqual(m["bars"][0][3], c["start"], delta=c["start"] * 1e-3)
            for o, h, l, cl, v in m["bars"]:
                self.assertTrue(l > 0 and l <= min(o, cl) and h >= max(o, cl) and v > 0, (c["key"], o, h, l, cl, v))
            self.assertEqual(len(m["dates"]), 600)

    def test_events_are_labelled_and_in_range(self):
        m = simulator.simulate("natgas", 5, 1500)
        self.assertTrue(m["events"])
        for e in m["events"]:
            self.assertTrue(0 <= e["bar"] < 1500 and e["label"] and e["pct"] != 0)

    def test_length_limits(self):
        for n in (1, simulator.MAX_BARS + 1):
            with self.assertRaises(ValueError):
                simulator.simulate("corn", 1, n)

    def test_dates_are_weekdays_and_increasing(self):
        import datetime
        d = simulator.business_dates(30)
        self.assertEqual(d, sorted(set(d)))
        self.assertTrue(all(datetime.date.fromisoformat(x).weekday() < 5 for x in d))

    def _stats(self, key, seeds=8, n=1500):
        vols, reverting = [], []
        for s in range(seeds):
            c = [b[3] for b in simulator.simulate(key, s, n)["bars"]]
            r = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
            vols.append(statistics.pstdev(r) * math.sqrt(252))
            reverting.append(statistics.pstdev([math.log(x) for x in c]))
        return statistics.fmean(vols), statistics.fmean(reverting)

    def test_realised_volatility_is_near_the_profile(self):
        for key in ("corn", "wti", "gold"):
            vol, _ = self._stats(key)
            target = commodities.get(key)["sigma"]
            self.assertTrue(0.7 * target < vol < 1.5 * target, (key, vol, target))

    def test_energy_reverts_more_than_metals_wander(self):
        _, wti_spread = self._stats("wti", n=2000)
        _, gold_spread = self._stats("gold", n=2000)
        self.assertLess(wti_spread, 0.6)                                           # stays within a band
        # per unit of daily volatility, the reverting market covers much less ground than the trending one
        self.assertLess(wti_spread / commodities.get("wti")["sigma"], gold_spread / commodities.get("gold")["sigma"])

    def test_agriculture_has_a_yearly_cycle(self):
        # average the detrended log price by position in the 252-day year over many markets: the corn curve should have a clear swing
        buckets = [[] for _ in range(12)]
        for s in range(40):
            c = [math.log(b[3]) for b in simulator.simulate("corn", s, 252 * 3)["bars"]]
            for i, x in enumerate(c):
                buckets[(i % 252) * 12 // 252].append(x - c[0])
        means = [statistics.fmean(b) for b in buckets]
        self.assertGreater(max(means) - min(means), 0.05)

    def test_volatility_clusters(self):
        # absolute returns are positively autocorrelated when volatility clusters
        acs = []
        for s in range(10):
            c = [b[3] for b in simulator.simulate("natgas", s, 1500)["bars"]]
            a = [abs(math.log(c[i] / c[i - 1])) for i in range(1, len(c))]
            ma = statistics.fmean(a)
            num = sum((a[i] - ma) * (a[i - 1] - ma) for i in range(1, len(a)))
            acs.append(num / sum((x - ma) ** 2 for x in a))
        self.assertGreater(statistics.fmean(acs), 0.05)


class Indicators(unittest.TestCase):
    def test_sma_and_ema_hand_values(self):
        v = [1, 2, 3, 4, 5]
        self.assertEqual(I.sma(v, 3), [None, None, 2.0, 3.0, 4.0])
        e = I.ema(v, 3)                                                           # seed = SMA(3) = 2, k = 0.5
        self.assertEqual(e[:2], [None, None])
        self.assertAlmostEqual(e[2], 2.0)
        self.assertAlmostEqual(e[3], 3.0)
        self.assertAlmostEqual(e[4], 4.0)

    def test_rsi_extremes_and_midpoint(self):
        up = list(range(1, 40))
        self.assertEqual(I.rsi(up)[-1], 100.0)
        self.assertAlmostEqual(I.rsi(list(range(40, 1, -1)))[-1], 0.0)
        zig = [10, 11] * 30
        self.assertTrue(40 < I.rsi(zig)[-1] < 60)

    def test_rsi_matches_a_textbook_example(self):
        # classic Wilder worked example (14-period); first RSI value is 70.46
        closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
        self.assertAlmostEqual(I.rsi(closes, 14)[14], 70.46, places=1)

    def test_bollinger_and_zscore_use_population_sd(self):
        v = [2, 4, 4, 4, 5, 5, 7, 9]                                              # mean 5, population sd 2
        mid, up, lo, pct = I.bollinger(v, 8, 2.0)
        self.assertAlmostEqual(mid[-1], 5.0)
        self.assertAlmostEqual(up[-1], 9.0)
        self.assertAlmostEqual(lo[-1], 1.0)
        self.assertAlmostEqual(pct[-1], 1.0)
        self.assertAlmostEqual(I.zscore(v, 8)[-1], 2.0)

    def test_rolling_sd_matches_the_statistics_module_on_big_prices(self):
        v = [2300 + math.sin(i) * 15 for i in range(200)]
        mid, up, lo, _ = I.bollinger(v, 20)
        for i in (19, 100, 199):
            self.assertAlmostEqual((up[i] - mid[i]) / 2, statistics.pstdev(v[i - 19:i + 1]), places=6)

    def test_atr_true_range_with_a_gap(self):
        high, low, close = [10, 12, 14], [9, 11, 13], [9.5, 11.5, 13.5]
        out = I.atr(high, low, close, 2)
        # TR: bar0 = 1, bar1 = max(1, |12-9.5|, |11-9.5|) = 2.5 ; ATR2 at bar 1 = 1.75
        self.assertAlmostEqual(out[1], 1.75)
        self.assertAlmostEqual(out[2], (1.75 * 1 + 2.5) / 2)

    def test_macd_zero_for_a_flat_series_and_positive_in_an_uptrend(self):
        line, sig, hist = I.macd([5.0] * 80)
        self.assertAlmostEqual(line[-1], 0.0)
        up = [100 * 1.01 ** i for i in range(120)]
        self.assertGreater(I.macd(up)[0][-1], 0)

    def test_realised_vol_of_a_constant_growth_series_is_zero(self):
        self.assertAlmostEqual(I.realised_vol([100 * 1.01 ** i for i in range(60)])[-1], 0.0, places=9)

    def test_drawdown(self):
        self.assertEqual(I.drawdown([1, 2, 1, 3, 1.5]), [0, 0, -0.5, 0, -0.5])

    def test_seasonal_tendency_needs_more_than_a_year_and_finds_a_repeating_pattern(self):
        flat = [100.0] * 300
        self.assertIsNone(I.seasonal_tendency(flat, 100))
        # a perfect 252-bar cycle: the tendency at t equals the next 21 bars' return one year earlier
        cyc = [100 + 10 * math.sin(2 * math.pi * i / 252) for i in range(700)]
        t = 600
        tend = I.seasonal_tendency(cyc, t, window=0)
        expect = (cyc[t - 252 + 21] / cyc[t - 252] - 1 + cyc[t - 504 + 21] / cyc[t - 504] - 1) / 2
        self.assertAlmostEqual(tend, expect)

    def test_no_look_ahead_every_indicator_at_t_ignores_later_bars(self):
        bars = simulator.simulate("copper", 4, 600)["bars"]
        full = I.compute(bars)
        for cut in (80, 250, 420):
            part = I.compute(bars[:cut])
            for name, series in full.items():
                for i in (cut - 1, cut - 5, cut // 2):
                    a, b = series[i], part[name][i]
                    if a is None or b is None:
                        self.assertEqual(a, b, (name, i))
                    else:
                        self.assertAlmostEqual(a, b, places=7, msg=(name, i))

    def test_compute_lengths(self):
        bars = simulator.simulate("gold", 2, 350)["bars"]
        for name, s in I.compute(bars).items():
            self.assertEqual(len(s), 350, name)


if __name__ == "__main__":
    unittest.main()
