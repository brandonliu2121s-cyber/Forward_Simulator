"""Analysis signals, the paper account, backtesting and metrics. Includes no-look-ahead checks and hand-computed accounting."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from csim import account as A, analysis, backtest as B, commodities, indicators as I, simulator  # noqa: E402


def flat_bars(n, price=100.0, rng=1.0):
    return [[price, price + rng, price - rng, price, 1000] for _ in range(n)]


class Analysis(unittest.TestCase):
    def setUp(self):
        self.m = simulator.simulate("copper", 5, 600)
        self.ind = I.compute(self.m["bars"])

    def test_weights_sum_to_one_for_every_group(self):
        for g, w in analysis.WEIGHTS.items():
            self.assertAlmostEqual(sum(w.values()), 1.0, msg=g)
        self.assertEqual(set(analysis.WEIGHTS), set(commodities.GROUPS))

    def test_deterministic_and_complete(self):
        a, b = analysis.analyze(self.ind, self.m["bars"], 400, "copper"), analysis.analyze(self.ind, self.m["bars"], 400, "copper")
        self.assertEqual(a, b)
        self.assertIn(a["signal"], ("Buy", "Sell", "Hold"))
        self.assertTrue(-100 <= a["score"] <= 100)
        self.assertEqual([v["name"] for v in a["votes"]], ["trend", "momentum", "reversion", "season"])
        for v in a["votes"]:
            self.assertTrue(-1 <= v["vote"] <= 1 and v["reason"])
        self.assertTrue(a["summary"] and a["change_mind"] and a["levels"]["support"] < a["levels"]["resistance"])
        self.assertAlmostEqual(a["score"], sum(v["contribution"] for v in a["votes"]), delta=0.2)

    def test_too_little_history_is_a_hold_with_an_explanation(self):
        a = analysis.analyze(self.ind, self.m["bars"], 10, "copper")
        self.assertEqual((a["signal"], a["score"]), ("Hold", 0.0))
        self.assertIn("history", a["summary"])

    def test_no_look_ahead_signal_at_t_is_the_same_on_a_truncated_market(self):
        full = analysis.signal_series(self.ind, self.m["bars"], "copper")
        for cut in (150, 320, 480):
            part_bars = self.m["bars"][:cut]
            part = analysis.signal_series(I.compute(part_bars), part_bars, "copper")
            for t in (cut - 1, cut - 10, 100):
                if full[t] is None:
                    self.assertIsNone(part[t])
                else:
                    self.assertAlmostEqual(full[t], part[t], places=5)
        a = analysis.analyze(self.ind, self.m["bars"], 300, "copper")
        b = analysis.analyze(I.compute(self.m["bars"][:301]), self.m["bars"][:301], 300, "copper")
        self.assertEqual((a["signal"], a["score"]), (b["signal"], b["score"]))

    def test_a_steady_uptrend_is_a_buy_for_metals(self):
        bars = [[100 * 1.002 ** i, 100 * 1.002 ** i * 1.004, 100 * 1.002 ** i * 0.996, 100 * 1.002 ** i * 1.001, 1000] for i in range(400)]
        for i, b in enumerate(bars):                       # add small noise so volatility is not zero
            k = 1 + 0.004 * math.sin(i * 1.7)
            bars[i] = [x * k for x in b[:4]] + [b[4]]
        ind = I.compute(bars)
        a = analysis.analyze(ind, bars, 399, "gold")
        self.assertEqual(a["signal"], "Buy")
        self.assertGreater(next(v for v in a["votes"] if v["name"] == "trend")["vote"], 0.3)

    def test_a_sharp_oversold_drop_in_energy_leans_toward_buying_the_dip(self):
        bars = [[x, x * 1.005, x * 0.995, x, 1000] for x in [80 + 2 * math.sin(i / 6) for i in range(330)]]
        for i in range(330, 345):                          # fifteen straight falls
            x = bars[-1][3] * 0.985
            bars.append([x, x * 1.004, x * 0.996, x, 1000])
        ind = I.compute(bars)
        a = analysis.analyze(ind, bars, len(bars) - 1, "wti")
        rev = next(v for v in a["votes"] if v["name"] == "reversion")
        self.assertGreater(rev["vote"], 0.2)
        self.assertLess(next(v for v in a["votes"] if v["name"] == "trend")["vote"], 0)         # the trend vote disagrees, as it should

    def test_signals_are_not_always_hold_and_not_always_the_same_way(self):
        seen = set()
        for c in commodities.COMMODITIES:
            m = simulator.simulate(c["key"], 9, 600)
            seen |= {analysis.label_for(s) for s in analysis.signal_series(I.compute(m["bars"]), m["bars"], c["key"])}
        self.assertEqual(seen - {None}, {"Buy", "Sell", "Hold"})


class AccountTests(unittest.TestCase):
    ZERO = dict(commission=0, fee_bps=0, slippage_bps=0)

    def bars(self):
        # bar: open, high, low, close
        return [[100, 101, 99, 100, 1], [101, 103, 100, 102, 1], [102, 106, 101, 105, 1], [105, 106, 98, 99, 1], [99, 100, 90, 92, 1], [92, 95, 91, 94, 1]]

    def test_market_order_fills_at_the_next_open_not_the_same_bar(self):
        r = A.run_account(self.bars(), 10, [dict(id=1, bar=0, side="buy", qty=2)], 0, 3, costs=self.ZERO)
        self.assertEqual(r["fills"][0]["bar"], 1)
        self.assertEqual(r["fills"][0]["price"], 101)
        self.assertEqual(r["account"]["qty"], 2)

    def test_hand_computed_round_trip_with_costs(self):
        costs = dict(commission=2.0, fee_bps=10, slippage_bps=100)             # 1% slippage, 10 bps fee
        r = A.run_account(self.bars(), 10, [dict(id=1, bar=0, side="buy", qty=1), dict(id=2, bar=2, side="sell", qty=1)], 0, 4, costs=costs)
        buy_px, sell_px = 101 * 1.01, 105 * 0.99                               # next opens with slippage against us
        fee_buy, fee_sell = 2 + buy_px * 10 * 0.001, 2 + sell_px * 10 * 0.001
        expected = 100000 + 10 * (sell_px - buy_px) - fee_buy - fee_sell
        self.assertAlmostEqual(r["account"]["equity"], expected, places=1)
        self.assertEqual(r["account"]["qty"], 0)
        self.assertAlmostEqual(r["account"]["realised"], 10 * (sell_px - buy_px) - fee_buy - fee_sell, places=1)

    def test_accounting_invariant_cash_plus_position_equals_equity_every_bar(self):
        m = simulator.simulate("wti", 3, 400)
        orders = [dict(id=i + 1, bar=20 + i * 15, side="buy" if i % 2 == 0 else "sell", qty=3 + i % 4) for i in range(18)]
        r = A.run_account(m["bars"], 100, orders, 10, 399)
        for row in r["equity"]:
            self.assertAlmostEqual(row["cash"] + row["qty"] * 100 * row["close"], row["equity"], delta=0.02)

    def test_short_position_profits_when_price_falls(self):
        r = A.run_account(self.bars(), 10, [dict(id=1, bar=2, side="sell", qty=1)], 0, 5, costs=self.ZERO)
        self.assertEqual(r["account"]["qty"], -1)
        self.assertAlmostEqual(r["account"]["equity"], 100000 + 10 * (105 - 94) * -1 * -1 - 0, places=2)   # sold at 105 (bar 3 open), marked at 94

    def test_stop_order_triggers_on_a_gap_at_the_open(self):
        # long from bar 1 open (101); stop at 100 placed after bar 1; bar 4 opens at 99 (below the stop) so it fills at the open, not at 100
        orders = [dict(id=1, bar=0, side="buy", qty=1), dict(id=2, bar=1, side="sell", qty=1, type="stop", price=100)]
        r = A.run_account(self.bars(), 10, orders, 0, 5, costs=self.ZERO)
        stop = next(f for f in r["fills"] if f["id"] == 2)
        self.assertEqual((stop["bar"], stop["price"]), (3, 100))               # bar 3 low is 98: triggers inside the bar at the stop price (open 105 > 100)
        self.assertEqual(r["account"]["qty"], 0)

    def test_stop_gap_fills_at_the_worse_open(self):
        bars = [[100, 101, 99, 100, 1], [100, 101, 99, 100, 1], [90, 91, 88, 89, 1], [89, 90, 88, 89, 1]]
        orders = [dict(id=1, bar=0, side="buy", qty=1), dict(id=2, bar=1, side="sell", qty=1, type="stop", price=95)]
        r = A.run_account(bars, 10, orders, 0, 3, costs=self.ZERO)
        self.assertEqual(next(f for f in r["fills"] if f["id"] == 2)["price"], 90)      # gapped through the stop: filled at the open

    def test_limit_order_waits_and_fills_at_its_price_or_better(self):
        orders = [dict(id=1, bar=0, side="buy", qty=1, type="limit", price=95)]
        r = A.run_account(self.bars(), 10, orders, 0, 5, costs=self.ZERO)
        self.assertEqual(r["fills"][0]["bar"], 4)                              # first bar whose low (90) trades through 95
        self.assertEqual(r["fills"][0]["price"], 95)                           # opened at 99, so the limit price applies
        gap = A.run_account([[100, 101, 99, 100, 1], [90, 92, 89, 91, 1]], 10, orders, 0, 1, costs=self.ZERO)
        self.assertEqual(gap["fills"][0]["price"], 90)                         # opened below the limit: better price at the open

    def test_cancel_stops_a_working_order(self):
        orders = [dict(id=1, bar=0, side="buy", qty=1, type="limit", price=95, cancel_bar=2)]
        r = A.run_account(self.bars(), 10, orders, 0, 5, costs=self.ZERO)
        self.assertEqual(r["fills"], [])
        self.assertEqual(r["working"], [])

    def test_a_cancel_on_the_last_bar_removes_the_order_straight_away(self):
        orders = [dict(id=1, bar=0, side="buy", qty=1, type="limit", price=50, cancel_bar=2)]
        r = A.run_account(self.bars(), 10, orders, 0, 2, costs=self.ZERO)          # viewing bar 2: cancelled at its close
        self.assertEqual(r["working"], [])
        still = A.run_account(self.bars(), 10, [dict(id=1, bar=0, side="buy", qty=1, type="limit", price=50)], 0, 2, costs=self.ZERO)
        self.assertEqual(len(still["working"]), 1)

    def test_leverage_limit_rejects_oversized_orders(self):
        r = A.run_account(flat_bars(5), 100, [dict(id=1, bar=0, side="buy", qty=50000)], 0, 4, cash=100000)
        self.assertEqual(r["fills"], [])
        self.assertIn("exceed", r["rejected"][0]["reason"])
        ok = A.run_account(flat_bars(5), 100, [dict(id=1, bar=0, side="buy", qty=20)], 0, 4)        # 20 x 100 x 100 = 200k = 2x
        self.assertEqual(len(ok["fills"]), 1)

    def test_invalid_orders_are_rejected_not_crashing(self):
        r = A.run_account(flat_bars(5), 100, [dict(id=1, bar=0, side="hold", qty=1), dict(id=2, bar=0, side="buy", qty=0), dict(id=3, bar=0, side="buy", qty=1, type="stop")], 0, 4)
        self.assertEqual(len(r["rejected"]), 3)
        self.assertEqual(r["fills"], [])

    def test_adding_blends_the_average_and_flipping_realises_the_closed_part(self):
        bars = [[100, 101, 99, 100, 1], [100, 101, 99, 100, 1], [110, 111, 109, 110, 1], [120, 121, 119, 120, 1], [120, 121, 119, 120, 1]]
        orders = [dict(id=1, bar=0, side="buy", qty=1), dict(id=2, bar=1, side="buy", qty=1), dict(id=3, bar=2, side="sell", qty=3)]
        r = A.run_account(bars, 10, orders, 0, 4, costs=self.ZERO)
        # buys fill at 100 (bar 1) and 110 (bar 2): average 105; sell 3 at 120 (bar 3): closes 2 lots (+150 each lot-pair: 2*10*15) and goes short 1
        self.assertEqual(r["account"]["qty"], -1)
        self.assertAlmostEqual(r["account"]["realised"], 2 * 10 * (120 - 105), places=2)
        self.assertAlmostEqual(r["account"]["avg"], 120)

    def test_bad_ranges_and_cash(self):
        with self.assertRaises(ValueError):
            A.run_account(flat_bars(5), 10, [], 3, 9)
        with self.assertRaises(ValueError):
            A.run_account(flat_bars(5), 10, [], 0, 4, cash=5)
        with self.assertRaises(ValueError):
            A.clean_costs(dict(commission=-1))


class Metrics(unittest.TestCase):
    def test_hand_computed_metrics(self):
        rows = [dict(bar=i, equity=v, qty=1 if i in (1, 2) else 0) for i, v in enumerate([100, 110, 99, 121])]
        m = B.metrics(rows, [], 100)
        self.assertAlmostEqual(m["total_return"], 0.21)
        self.assertAlmostEqual(m["max_drawdown"], 99 / 110 - 1)
        self.assertEqual(m["longest_drawdown_bars"], 1)
        self.assertAlmostEqual(m["exposure"], 0.5)

    def test_round_trips_and_trade_stats(self):
        bars = flat_bars(10)
        fills = [dict(bar=1, side="buy", qty=2, price=100, realised=-1, position_after=2), dict(bar=3, side="sell", qty=2, price=110, realised=39, position_after=0),
                 dict(bar=4, side="sell", qty=1, price=110, realised=-1, position_after=-1), dict(bar=6, side="buy", qty=1, price=115, realised=-6, position_after=0)]
        trips = B.round_trips(fills, bars, 10, 9)
        self.assertEqual([(t["side"], t["pnl"], t["open"]) for t in trips], [("long", 38, False), ("short", -7, False)])
        rows = [dict(bar=i, equity=100000 + i, qty=0) for i in range(10)]
        m = B.metrics(rows, trips, 100000)
        self.assertEqual((m["trades"], m["win_rate"]), (2, 0.5))
        self.assertAlmostEqual(m["profit_factor"], 38 / 7)

    def test_flip_through_zero_ends_one_trade_and_starts_another(self):
        fills = [dict(bar=1, side="buy", qty=1, price=100, realised=0, position_after=1), dict(bar=2, side="sell", qty=3, price=110, realised=10, position_after=-2)]
        trips = B.round_trips(fills, flat_bars(5), 10, 4)
        self.assertEqual([t["side"] for t in trips], ["long", "short"])
        self.assertTrue(trips[1]["open"] and not trips[0]["open"])


class Backtests(unittest.TestCase):
    def setUp(self):
        self.m = simulator.simulate("gold", 2, 600)
        self.ind = I.compute(self.m["bars"])

    def test_buy_and_hold_equals_the_price_ratio_when_costs_are_zero(self):
        zero = dict(commission=0, fee_bps=0, slippage_bps=0)
        r = B.backtest(self.m["bars"], self.ind, "gold", "buy_hold", {}, 300, 599, 100000, zero, 0.5)
        lot = commodities.get("gold")["lot"]
        qty = r["fills"][0]["qty"]
        entry = self.m["bars"][301][0]
        self.assertEqual(r["fills"][0]["bar"], 301)                            # decided at the close of bar 300, filled at bar 301's open
        expected = 100000 + qty * lot * (self.m["bars"][599][3] - entry)
        self.assertAlmostEqual(r["equity"][-1][1], expected, places=1)

    def test_costs_reduce_results(self):
        zero = dict(commission=0, fee_bps=0, slippage_bps=0)
        a = B.backtest(self.m["bars"], self.ind, "gold", "sma_cross", dict(fast=10, slow=50), 300, 599, 100000, zero, 0.5)
        b = B.backtest(self.m["bars"], self.ind, "gold", "sma_cross", dict(fast=10, slow=50), 300, 599, 100000, dict(commission=20, fee_bps=20, slippage_bps=50), 0.5)
        self.assertLess(b["metrics"]["total_return"], a["metrics"]["total_return"])

    def test_strategies_cannot_see_the_future(self):
        """Replace everything after bar 450 with a different market: equity up to bar 451 (the last fill that depends on bar <= 450) must not change."""
        other = simulator.simulate("gold", 99, 600)["bars"]
        alt = self.m["bars"][:451] + other[451:]
        ind2 = I.compute(alt)
        for name, params in (("signal", None), ("sma_cross", dict(fast=10, slow=50)), ("rsi_reversion", None), ("breakout", None)):
            a = B.backtest(self.m["bars"], self.ind, "gold", name, params, 300, 599, 100000, None, 0.5, True)
            b = B.backtest(alt, ind2, "gold", name, params, 300, 599, 100000, None, 0.5, True)
            ea, eb = dict(map(tuple, a["equity"])), dict(map(tuple, b["equity"]))
            for bar in range(300, 451):
                self.assertEqual(ea[bar], eb[bar], (name, bar))

    def test_short_selling_is_only_used_when_allowed(self):
        down = [[100 * 0.997 ** i * f for f in (1, 1.004, 0.996, 1)] + [1000] for i in range(500)]
        ind = I.compute(down)
        flat = B.backtest(down, ind, "gold", "sma_cross", dict(fast=10, slow=50), 300, 499, 100000, None, 0.5, False)
        short = B.backtest(down, ind, "gold", "sma_cross", dict(fast=10, slow=50), 300, 499, 100000, None, 0.5, True)
        self.assertEqual(flat["fills"], [])
        self.assertTrue(any(f["side"] == "sell" for f in short["fills"]))
        self.assertGreater(short["metrics"]["total_return"], 0)

    def test_compare_includes_buy_and_hold_and_drawdown(self):
        r = B.compare(self.m["bars"], self.ind, "gold", "signal", None, 300, 599, 100000, None, 0.5, False)
        self.assertIn("metrics", r["buy_hold"])
        self.assertEqual(len(r["drawdown"]), len(r["equity"]))
        self.assertTrue(all(d[1] <= 0 for d in r["drawdown"]))

    def test_input_validation(self):
        for kw in (dict(strategy="nope"), dict(strategy="sma_cross", params=dict(fast=50, slow=10)), dict(strategy="rsi_reversion", params=dict(low="x")), dict(strategy="signal", params=dict(enter=500))):
            with self.assertRaises(ValueError):
                B.backtest(self.m["bars"], self.ind, "gold", kw["strategy"], kw.get("params"), 300, 599)
        with self.assertRaises(ValueError):
            B.backtest(self.m["bars"], self.ind, "gold", "buy_hold", {}, 300, 599, alloc=9)

    def test_monte_carlo_is_deterministic_and_well_formed(self):
        a = B.monte_carlo("wti", "sma_cross", dict(fast=10, slow=50), n=12, days=150, seed0=5)
        b = B.monte_carlo("wti", "sma_cross", dict(fast=10, slow=50), n=12, days=150, seed0=5)
        self.assertEqual(a, b)
        self.assertEqual(sum(a["histogram"]["counts"]), 12)
        s = a["summary"]
        self.assertTrue(s["p5"] <= s["median"] <= s["p95"] and 0 <= s["profitable"] <= 1)
        with self.assertRaises(ValueError):
            B.monte_carlo("wti", "signal", None, n=2)

    def test_the_sweep_reports_in_sample_and_out_of_sample(self):
        sw = B.sweep_sma(self.m["bars"], self.ind, "gold", 300, 599, 100000, None, 0.5, False)
        self.assertEqual(len(sw["rows"]), 12 - 0)                              # 3 fast x 4 slow, all fast < slow
        self.assertEqual(sw["rows"][0]["rank_train"], 1)
        self.assertTrue(all(sw["rows"][i]["train"] >= sw["rows"][i + 1]["train"] for i in range(11)))
        self.assertIn("second half", sw["note"])


if __name__ == "__main__":
    unittest.main()
