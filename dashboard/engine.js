/* Simulation engine for the forwards market-making dashboard.
 * A line-for-line port of reference_model.py (which the Excel workbook is also verified against).
 * Pure functions, no DOM: runs in the browser and in Node (see tests/test_dashboard_engine.py). */
const Engine = (function () {
  // Excel ROUND semantics (half away from zero)
  const rnd = (x) => (x < 0 ? -Math.round(-x) : Math.round(x));
  const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));

  /** F = S x (1 + rateB x d/basisB) / (1 + rateA x d/basisA): interest-rate parity (FX) or cost of carry (commodity). */
  function fairForward(spot, p) {
    const d = p.tenor_days;
    return (spot * (1 + (p.rate_b * d) / p.basis_b)) / (1 + (p.rate_a * d) / p.basis_a);
  }

  function skewTicks(pos, p) {
    return -clamp(pos / p.pos_limit, -1, 1) * p.max_skew_ticks;
  }

  function quote(fwd, pos, p) {
    const skew = skewTicks(pos, p);
    const bid = rnd(fwd / p.tick + skew - p.spread_ticks / 2) * p.tick;
    return { skew, bid, ask: bid + p.spread_ticks * p.tick };
  }

  function simulate(zs, acts, p) {
    const rows = [];
    let spot = p.spot_init;
    let fwdPrev = fairForward(spot, p);
    let pos = p.start_pos, cum = 0, halted = 0;
    const hedgeTarget = p.hedge_target_pct * p.pos_limit;
    for (let i = 0; i < zs.length; i++) {
      const z = zs[i], act = acts[i];
      spot = spot + z * p.step_vol_ticks * p.tick;
      const fwd = fairForward(spot, p);
      const q = quote(fwd, pos, p);
      const live = halted === 0;
      let fill = 0;
      if (live && act === 'BUY') fill = -p.clip;          // client lifts our ask: we go shorter
      else if (live && act === 'SELL') fill = p.clip;     // client hits our bid: we go longer
      const posClient = pos + fill;
      let edge = 0;
      if (fill < 0) edge = Math.abs(fill) * (q.ask - fwd);
      else if (fill > 0) edge = fill * (fwd - q.bid);
      const mtm = pos * (fwd - fwdPrev);
      const cumPre = cum + mtm + edge;
      const posBreach = Math.abs(posClient) > p.pos_limit ? 1 : 0;
      const lossBreach = !halted && cumPre <= -p.loss_limit ? 1 : 0;
      let hedge = 0;
      if (lossBreach) hedge = -posClient;
      else if (posBreach) hedge = -(posClient - (posClient > 0 ? 1 : -1) * hedgeTarget);
      const hedgeCost = -Math.abs(hedge) * p.hedge_cost_ticks * p.tick;
      const posClose = posClient + hedge;
      const stepPnl = mtm + edge + hedgeCost;
      cum += stepPnl;
      halted = p.halt_on_loss === 1 ? Math.max(halted, lossBreach) : 0;
      rows.push({
        step: i + 1, z, act, spot, fwd, pos_open: pos, util: pos / p.pos_limit, skew: q.skew, bid: q.bid, ask: q.ask,
        live, fill, edge, mtm, pos_breach: posBreach, loss_breach: lossBreach, hedge, hedge_cost: hedgeCost,
        pos_client: posClient, pos_close: posClose, step_pnl: stepPnl, cum, halted,
        trigger: lossBreach ? 'LOSS LIMIT' : posBreach ? 'POSITION LIMIT' : '',
      });
      pos = posClose;
      fwdPrev = fwd;
    }
    return rows;
  }

  function summarize(rows, p) {
    const n = rows.length;
    const sum = (k) => rows.reduce((a, r) => a + r[k], 0);
    const fills = rows.filter((r) => r.fill !== 0);
    const lossRow = rows.find((r) => r.loss_breach);
    const posHedges = rows.filter((r) => r.pos_breach && !r.loss_breach).length;
    const lossFlat = rows.filter((r) => r.loss_breach).length;
    const minCum = Math.min(0, ...rows.map((r) => r.cum));
    const peakAfterClient = Math.max(0, ...rows.map((r) => Math.abs(r.pos_client)));
    const peakClose = Math.max(0, ...rows.map((r) => Math.abs(r.pos_close)));
    const last = rows[n - 1] || { cum: 0, pos_close: p.start_pos, fwd: fairForward(p.spot_init, p), spot: p.spot_init };
    const s = {
      n, cum: last.cum, capture: sum('edge'), mtm: sum('mtm'), hedgeCost: sum('hedge_cost'),
      fills: fills.length, buys: rows.filter((r) => r.fill < 0).length, sells: rows.filter((r) => r.fill > 0).length,
      volume: fills.reduce((a, r) => a + Math.abs(r.fill), 0), hedgeVolume: rows.reduce((a, r) => a + Math.abs(r.hedge), 0),
      posHedges, lossFlat, lossStep: lossRow ? lossRow.step : null,
      peakAfterClient, peakClose, peakUtil: peakAfterClient / p.pos_limit,
      meanUtil: n ? rows.reduce((a, r) => a + Math.abs(r.pos_close) / p.pos_limit, 0) / n : 0,
      minCum, lossUsed: Math.max(0, -minCum) / p.loss_limit,
      maxSkewUsed: p.max_skew_ticks ? Math.max(0, ...rows.map((r) => Math.abs(r.skew))) / p.max_skew_ticks : 0,
      liveSteps: rows.filter((r) => r.live).length, halted: !!(last.halted),
      hitRate: n ? fills.length / n : 0, endPos: last.pos_close, endFwd: last.fwd, endSpot: last.spot,
    };
    s.health = n ? Math.round((100 * s.liveSteps) / n) : 100;
    s.risk = riskScore(s);
    return s;
  }

  /** 0-100, higher = safer: half inventory headroom, half loss headroom, minus a penalty per limit event. */
  function riskScore(s) {
    const posHead = 1 - clamp(s.meanUtil, 0, 1);
    const lossHead = 1 - clamp(s.lossUsed, 0, 1);
    return clamp(Math.round(100 * (0.5 * posHead + 0.5 * lossHead) - 4 * s.posHedges - 10 * s.lossFlat), 0, 100);
  }

  /** Same scenario with the skew switched off: shows what inventory skew is worth. */
  function riskWithoutSkew(zs, acts, p) {
    const q = Object.assign({}, p, { max_skew_ticks: 0 });
    return summarize(simulate(zs, acts, q), q).risk;
  }

  // ---- scenario generation (browser RNG; the shipped default scenario comes from reference_model.py seed 277)
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function generateScenario(seed, n) {
    const rand = mulberry32(seed);
    const gauss = () => Math.sqrt(-2 * Math.log(1 - rand())) * Math.cos(2 * Math.PI * rand());
    const zs = [], acts = [];
    let bias = 0;
    for (let i = 0; i < n; i++) {
      zs.push(Math.round(gauss() * 10) / 10);
      if (rand() < 0.15) bias = [-1, 0, 1][Math.floor(rand() * 3)];
      if (rand() < 0.3) acts.push('NONE');
      else {
        const side = bias !== 0 && rand() < 0.65 ? bias : rand() < 0.5 ? -1 : 1;
        acts.push(side > 0 ? 'BUY' : 'SELL');
      }
    }
    return { zs, acts };
  }

  return { fairForward, skewTicks, quote, simulate, summarize, riskScore, riskWithoutSkew, generateScenario, rnd };
})();
if (typeof module !== 'undefined') module.exports = Engine;
