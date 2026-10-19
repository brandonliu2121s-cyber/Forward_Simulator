/* Import / export for the Forward Desk dashboard: CSV and JSON.  Pure functions, no DOM (tested in Node).
 *
 * Formats (all round-trip):
 *   scenario  CSV  step,move_sigma,action          JSON {"moves":[..],"actions":[..]}
 *   run       CSV  one row per step (re-importable as a scenario)    JSON {"summary":..,"steps":[..]}
 *   library   CSV  one row per instrument            JSON {"instruments":[..]}
 *   session   JSON instrument + overrides + globals + scenario + results
 * The scenario CSV matches columns A:C of the Excel workbook's Simulation sheet, and an exported Excel
 * "Instruments" sheet (percentages like 4.00%, "n/a" cells, extra computed columns) imports as a library.
 * Imported text is untrusted data: everything is validated, nothing is evaluated. */
const IO = (function () {
  const MAX_BYTES = 2 * 1024 * 1024, MAX_STEPS = 500, MAX_Z = 10;
  const PARAM_KEYS = ['spot_init', 'rate_a', 'rate_b', 'basis_a', 'basis_b', 'tenor_days', 'tick', 'clip', 'spread_ticks',
    'max_skew_ticks', 'pos_limit', 'loss_limit', 'hedge_cost_ticks', 'step_vol_ticks'];
  const GLOBAL_KEYS = ['hedge_target_pct', 'halt_on_loss', 'start_pos'];
  const LIB_COLS = ['name', 'type', 'unit', 'pnl', 'spot', 'rate_a', 'rate_b', 'basis_a', 'basis_b', 'tenor_days', 'tick', 'clip',
    'spread_ticks', 'max_skew_ticks', 'pos_limit', 'loss_limit', 'hedge_cost_ticks', 'step_vol_ticks', 'note'];
  const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const norm = (s) => String(s == null ? '' : s).toLowerCase().replace(/p\s*&\s*l/g, 'pnl').replace(/[^a-z0-9]/g, '');   // 'P&L' -> 'pnl'

  // header text (normalised) -> canonical instrument field. Covers our own CSV and the Excel Instruments sheet headers.
  const ALIAS = {
    name: 'name', instrument: 'name', type: 'type', unit: 'unit', positionunit: 'unit', pnl: 'pnl', pnlccy: 'pnl', pnlcurrency: 'pnl',
    spot: 'spot_init', spotinit: 'spot_init', ratea: 'rate_a', rateb: 'rate_b', basisa: 'basis_a', basisb: 'basis_b',
    daybasisa: 'basis_a', daybasisb: 'basis_b', tenordays: 'tenor_days', tenor: 'tenor_days', tick: 'tick', ticksize: 'tick',
    clip: 'clip', clipsize: 'clip', quotesize: 'clip', quotesizeunits: 'clip', spreadticks: 'spread_ticks',
    maxskewticks: 'max_skew_ticks', poslimit: 'pos_limit', positionlimit: 'pos_limit', positionlimitunits: 'pos_limit',
    losslimit: 'loss_limit', losslimitpnlccy: 'loss_limit', hedgecostticks: 'hedge_cost_ticks', stepvolticks: 'step_vol_ticks',
    note: 'note', sourcenote: 'note',
  };
  const RATE_KEYS = ['rate_a', 'rate_b'];

  // ------------------------------------------------------------------ CSV
  function parseCSV(text) {
    text = String(text).replace(/^﻿/, '');
    const first = text.split(/\r?\n/, 1)[0] || '';
    const delim = [',', ';', '\t'].map((d) => [d, first.split(d).length]).sort((a, b) => b[1] - a[1])[0][0];
    const rows = []; let row = [], f = '', q = false, any = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (q) {
        if (c === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += c;
      } else if (c === '"') { q = true; any = true; }
      else if (c === delim) { row.push(f); f = ''; any = true; }
      else if (c === '\n' || c === '\r') {
        if (c === '\r' && text[i + 1] === '\n') i++;
        row.push(f); f = '';
        if (any || row.some((x) => x !== '')) rows.push(row);
        row = []; any = false;
      } else { f += c; any = true; }
    }
    row.push(f);
    if (any || row.some((x) => x !== '')) rows.push(row);
    return rows;
  }
  const r12 = (v) => (typeof v === 'number' && Number.isFinite(v) ? Number(v.toPrecision(12)) : v);   // drop floating-point noise (1.2800116435630007 -> 1.28001164356)
  function csvCell(v) {
    if (v == null) return '';
    if (typeof v === 'number') return Number.isFinite(v) ? String(Object.is(v, -0) ? 0 : r12(v)) : '';
    let s = String(v);
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;                 // spreadsheet formula-injection guard
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  const toCSV = (headers, rows) => [headers.map(csvCell).join(',')].concat(rows.map((r) => r.map(csvCell).join(','))).join('\r\n') + '\r\n';
  const unguard = (s) => (typeof s === 'string' ? s.replace(/^'(?=[=+\-@])/, '') : s);

  // ------------------------------------------------------------------ value parsing
  function num(v) {
    if (typeof v === 'number') return v;
    if (typeof v !== 'string') return NaN;
    let s = v.trim();
    if (s === '' || /^n\/?a$/i.test(s)) return NaN;
    let pct = false;
    if (s.endsWith('%')) { pct = true; s = s.slice(0, -1).trim(); }
    if (/^-?\d{1,3}(,\d{3})+(\.\d+)?$/.test(s)) s = s.replace(/,/g, '');
    const n = Number(s);
    return pct ? n / 100 : n;
  }
  const MAX_NAME = 40;
  const clip = (s, n) => Array.from(s).slice(0, n).join('');            // by code point, so an emoji is never cut in half
  const cleanFull = (s) => String(s == null ? '' : s).replace(/[\u0000-\u001f\u007f]/g, '').trim();
  const cleanName = (s) => clip(cleanFull(s), MAX_NAME);
  const cleanTxt = (s, n) => clip(cleanFull(unguard(String(s == null ? '' : s))), n);

  /** Validate one instrument definition (flat object with canonical keys). Returns {ok:{...}} or {error:'...'} */
  function buildInstrument(raw, label) {
    const full = cleanFull(unguard(raw.name)), name = clip(full, MAX_NAME), shortened = Array.from(full).length > MAX_NAME;
    const at = label || name || '(unnamed)';
    if (!name) return { error: `${at}: missing name` };
    if (['__proto__', 'constructor', 'prototype'].includes(name)) return { error: `${at}: reserved name` };
    const t = String(raw.type == null ? '' : raw.type).trim();
    const type = /^fx$/i.test(t) ? 'FX' : /^commod/i.test(t) ? 'Commodity' : null;
    if (!type) return { error: `${name}: type must be FX or Commodity` };
    const unit = cleanTxt(raw.unit, 12);
    if (!unit) return { error: `${name}: missing position unit` };
    const pnl = cleanTxt(raw.pnl, 12) || (type === 'Commodity' ? 'USD' : '');
    if (!pnl) return { error: `${name}: missing P&L currency` };
    const params = {};
    for (const k of PARAM_KEYS) {
      const v = num(raw[k]);
      if (!Number.isFinite(v)) return { error: `${name}: ${k} is missing or not a number` };
      params[k] = v;
    }
    const pos = ['spot_init', 'tick', 'clip', 'pos_limit', 'loss_limit', 'tenor_days', 'basis_a', 'basis_b'];
    for (const k of pos) if (!(params[k] > 0)) return { error: `${name}: ${k} must be greater than 0` };
    for (const k of ['spread_ticks', 'max_skew_ticks', 'hedge_cost_ticks', 'step_vol_ticks']) if (params[k] < 0) return { error: `${name}: ${k} cannot be negative` };
    for (const k of RATE_KEYS) if (!(params[k] > -0.5 && params[k] < 1)) return { error: `${name}: ${k} = ${params[k]} is outside -50%..100%. Use a fraction (0.04) or a percent sign (4%).` };
    if (params.tenor_days > 3650) return { error: `${name}: tenor_days is unreasonably large` };
    return { ok: { name, type, unit, pnl, note: cleanTxt(raw.note, 240), params }, shortened };
  }

  // ------------------------------------------------------------------ scenario parsing
  function buildScenario(items, where) {
    const errors = [], warnings = [], zs = [], acts = [];
    items.forEach((it, i) => {
      const z = num(it.z), line = `${where} ${it.line == null ? i + 1 : it.line}`;
      if (!Number.isFinite(z) || Math.abs(z) > MAX_Z) { errors.push(`${line}: market move must be a number between -${MAX_Z} and ${MAX_Z} (got "${String(it.z).slice(0, 20)}")`); return; }
      const a = String(it.a == null ? '' : it.a).trim().toUpperCase();
      const act = a === 'BUY' || a === 'B' ? 'BUY' : a === 'SELL' || a === 'S' ? 'SELL' : a === 'NONE' || a === 'N' || a === '' || a === '-' ? 'NONE' : null;
      if (!act) { errors.push(`${line}: action must be BUY, SELL or NONE (got "${a.slice(0, 20)}")`); return; }
      zs.push(Math.round(z * 1e6) / 1e6); acts.push(act);
    });
    if (!errors.length && !zs.length) errors.push('No steps found.');
    if (zs.length > MAX_STEPS) { warnings.push(`Only the first ${MAX_STEPS} of ${zs.length} steps were kept.`); zs.length = MAX_STEPS; acts.length = MAX_STEPS; }
    return { zs, acts, errors, warnings };
  }

  function scenarioFromCSVRows(rows, canonCols, headers) {
    const norms = headers.map(norm);
    const mi = norms.findIndex((h) => h.includes('move') || h.includes('sigma') || h.includes('shock') || h === 'z');
    const ai = norms.findIndex((h) => h.includes('action'));
    if (mi < 0 || ai < 0) return null;
    const items = rows.slice(1).map((r, i) => ({ z: r[mi], a: r[ai], line: i + 2 }));
    return Object.assign({ kind: 'scenario', source: 'csv' }, buildScenario(items, 'Line'));
  }

  function scenarioFromJSON(o) {
    let items = null;
    const arr = (x) => (Array.isArray(x) ? x : null);
    if (arr(o)) items = o.map((r) => (r && typeof r === 'object' ? { z: firstOf(r, ['move_sigma', 'move', 'z', 'sigma', 'market_move']), a: firstOf(r, ['action', 'client_action', 'client']) } : { z: NaN, a: '' }));
    else if (o && typeof o === 'object') {
      const m = arr(o.moves) || arr(o.move_sigma) || arr(o.zs), a = arr(o.actions) || arr(o.acts);
      if (m && a) {
        if (m.length !== a.length) return { kind: 'scenario', zs: [], acts: [], errors: [`moves (${m.length}) and actions (${a.length}) must have the same length`], warnings: [] };
        items = m.map((z, i) => ({ z, a: a[i] }));
      } else if (arr(o.steps)) return scenarioFromJSON(o.steps);
    }
    if (!items) return null;
    return Object.assign({ kind: 'scenario', source: 'json' }, buildScenario(items, 'Step'));
  }
  const firstOf = (r, keys) => { for (const k of keys) if (own(r, k)) return r[k]; return undefined; };

  // ------------------------------------------------------------------ library parsing
  function canonRecord(obj) {                      // object with any alias keys (or nested params) -> canonical flat record
    const rec = {};
    const src = Object.assign({}, obj && typeof obj.params === 'object' && obj.params ? obj.params : {}, obj);
    for (const k of Object.keys(src)) {
      if (k === '__proto__') continue;
      const c = ALIAS[norm(k)];
      if (c && !own(rec, c)) rec[c] = src[k];
    }
    return rec;
  }
  function libraryFromRecords(recs) {
    const errors = [], warnings = [], list = [], seen = {};
    recs.forEach((r, i) => {
      const res = buildInstrument(r, `Row ${i + 1}`);
      if (res.error) { errors.push(res.error); return; }
      if (res.shortened) warnings.push(`${res.ok.name}: the name was longer than ${MAX_NAME} characters and was shortened.`);
      if (own(seen, res.ok.name)) { warnings.push(`${res.ok.name}: appears more than once, the last row wins.`); list[seen[res.ok.name]] = res.ok; return; }
      seen[res.ok.name] = list.length; list.push(res.ok);
    });
    if (!list.length && !errors.length) errors.push('No instruments found.');
    return { kind: 'library', instruments: list, errors, warnings, skipped: errors.length };
  }
  function libraryFromCSVRows(rows, canon) {
    const recs = rows.slice(1).map((r) => { const o = {}; canon.forEach((c, i) => { if (c && !own(o, c)) o[c] = r[i]; }); return o; });
    return libraryFromRecords(recs);
  }

  // ------------------------------------------------------------------ session parsing
  function sessionFromJSON(o) {
    const errors = [], warnings = [];
    const inst = typeof o.instrument === 'string' ? cleanName(o.instrument) : '';
    if (!inst) errors.push('Session has no "instrument".');
    let definition = null;
    if (o.instrument_definition && typeof o.instrument_definition === 'object') {
      const r = buildInstrument(canonRecord(o.instrument_definition), 'instrument_definition');
      if (r.error) errors.push(r.error);
      else if (r.ok.name !== inst) errors.push(`instrument_definition is for "${r.ok.name}" but the session instrument is "${inst}".`);
      else definition = r.ok;
    }
    const overrides = {};
    if (o.overrides != null) {
      if (typeof o.overrides !== 'object' || Array.isArray(o.overrides)) errors.push('"overrides" must be an object.');
      else for (const k of Object.keys(o.overrides)) {
        if (!PARAM_KEYS.includes(k)) { warnings.push(`Ignored unknown override "${k.slice(0, 30)}".`); continue; }
        const v = o.overrides[k];
        if (typeof v !== 'number' || !Number.isFinite(v)) errors.push(`Override ${k} must be a number.`);
        else overrides[k] = v;
      }
    }
    const globals = {};
    if (o.globals != null) {
      if (typeof o.globals !== 'object' || Array.isArray(o.globals)) errors.push('"globals" must be an object.');
      else for (const k of Object.keys(o.globals)) {
        if (!GLOBAL_KEYS.includes(k)) { warnings.push(`Ignored unknown setting "${k.slice(0, 30)}".`); continue; }
        const v = o.globals[k];
        if (typeof v !== 'number' || !Number.isFinite(v)) errors.push(`Setting ${k} must be a number.`);
        else if (k === 'hedge_target_pct' && (v < 0 || v > 1)) errors.push('hedge_target_pct must be between 0 and 1.');
        else if (k === 'halt_on_loss' && v !== 0 && v !== 1) errors.push('halt_on_loss must be 0 or 1.');
        else globals[k] = v;
      }
    }
    let scenario = null;
    if (o.scenario != null) {
      const sc = scenarioFromJSON(o.scenario);
      if (!sc) errors.push('Could not read "scenario" (expected moves and actions).');
      else { errors.push(...sc.errors); warnings.push(...sc.warnings); if (!sc.errors.length) scenario = { zs: sc.zs, acts: sc.acts, seed: typeof o.scenario.seed === 'number' ? o.scenario.seed : null, note: cleanTxt(o.scenario.note, 60) || 'Imported session' }; }
    }
    return { kind: 'session', instrument: inst, definition, overrides, globals, scenario, errors, warnings };
  }

  // ------------------------------------------------------------------ entry point
  function parseImport(text, fileName) {
    const fail = (m) => ({ kind: null, errors: [m], warnings: [] });
    text = String(text == null ? '' : text);
    if (text.length > MAX_BYTES) return fail('That is over 2 MB, which is more than this tool will read.');
    const t = text.trim();
    if (!t) return fail('Nothing to import: choose a file or paste some text.');
    if (/^[[{]/.test(t)) {
      let o;
      try { o = JSON.parse(t); } catch (e) { return fail('This looks like JSON but it is not valid: ' + String(e.message).slice(0, 120)); }
      if (Array.isArray(o)) {
        const f = o[0];
        if (f && typeof f === 'object' && (own(f, 'action') || own(f, 'client_action'))) return scenarioFromJSON(o);
        if (f && typeof f === 'object' && (own(f, 'name') || own(f, 'instrument'))) return libraryFromRecords(o.map((x) => canonRecord(x)));
        return fail('A JSON list must contain steps (move_sigma, action) or instruments (name, type, ...).');
      }
      if (o && typeof o === 'object') {
        if (o.format === 'forward-desk-session' || (own(o, 'instrument') && (own(o, 'scenario') || own(o, 'overrides')))) return sessionFromJSON(o);
        if (Array.isArray(o.instruments)) return libraryFromRecords(o.instruments.map((x) => canonRecord(x)));
        const sc = scenarioFromJSON(own(o, 'scenario') && o.scenario && typeof o.scenario === 'object' ? o.scenario : o);
        if (sc) return sc;
      }
      return fail('Unrecognised JSON. Expected a session, a scenario (moves + actions) or a library ({"instruments": [...]}).');
    }
    const rows = parseCSV(t);
    if (rows.length < 2) return fail('The CSV needs a header row and at least one data row.');
    const headers = rows[0], canon = headers.map((h) => ALIAS[norm(h)] || null);
    const paramHits = canon.filter((c) => PARAM_KEYS.includes(c)).length;
    if (canon.includes('name') && paramHits >= 5) return libraryFromCSVRows(rows, canon);
    const sc = scenarioFromCSVRows(rows, canon, headers);
    if (sc) return sc;
    return fail('Could not recognise the columns. A scenario needs "move" and "action" columns; a library needs name, type, unit, spot, rate_a, rate_b and the other instrument columns.');
  }

  // ------------------------------------------------------------------ exports
  const RUN_COLS = [['step', 'step'], ['move_sigma', 'z'], ['action', 'act'], ['spot', 'spot'], ['fair_forward', 'fwd'], ['open_position', 'pos_open'],
    ['skew_ticks', 'skew'], ['bid', 'bid'], ['ask', 'ask'], ['fill_units', 'fill'], ['spread_capture', 'edge'], ['mtm', 'mtm'], ['hedge_trigger', 'trigger'],
    ['hedge_units', 'hedge'], ['hedge_cost', 'hedge_cost'], ['close_position', 'pos_close'], ['step_pnl', 'step_pnl'], ['cum_pnl', 'cum']];
  const runHeaders = () => RUN_COLS.map((c) => c[0]).concat('status');
  const runRow = (r) => RUN_COLS.map((c) => r[c[1]]).concat(r.live ? 'LIVE' : 'HALTED');
  const runObj = (r) => { const o = {}; RUN_COLS.forEach((c) => { o[c[0]] = r12(r[c[1]]); }); o.status = r.live ? 'LIVE' : 'HALTED'; return o; };
  const iso = () => new Date().toISOString();

  const exportRunCSV = (rows) => toCSV(runHeaders(), rows.map(runRow));
  const exportRunJSON = (meta, rows) => JSON.stringify({ format: 'forward-desk-run', version: 1, exported: iso(), instrument: meta.instrument, unit: meta.unit, pnl_currency: meta.pnl,
    parameters: meta.params, globals: meta.globals, summary: meta.summary, steps: rows.map(runObj) }, null, 2);
  const exportScenarioCSV = (zs, acts) => toCSV(['step', 'move_sigma', 'action'], zs.map((z, i) => [i + 1, z, acts[i]]));
  const exportScenarioJSON = (sc) => JSON.stringify({ format: 'forward-desk-scenario', version: 1, exported: iso(), seed: sc.seed, note: sc.note, moves: sc.zs, actions: sc.acts }, null, 2);
  const flatInst = (i) => { const o = { name: i.name, type: i.type, unit: i.unit, pnl: i.pnl }; o.spot = i.params.spot_init; PARAM_KEYS.slice(1).forEach((k) => { o[k] = i.params[k]; }); o.note = i.note || ''; return o; };
  const exportLibraryCSV = (list) => toCSV(LIB_COLS, list.map((i) => { const o = flatInst(i); return LIB_COLS.map((c) => o[c]); }));
  const exportLibraryJSON = (list) => JSON.stringify({ format: 'forward-desk-library', version: 1, exported: iso(), instruments: list.map(flatInst) }, null, 2);
  const exportSessionJSON = (s) => JSON.stringify({ format: 'forward-desk-session', version: 1, exported: iso(), instrument: s.instrument, instrument_definition: flatInst(s.definition),
    overrides: s.overrides, globals: s.globals, scenario: { seed: s.scenario.seed, note: s.scenario.note, moves: s.scenario.zs, actions: s.scenario.acts },
    summary: s.summary, steps: s.rows.map(runObj) }, null, 2);

  return { parseCSV, toCSV, parseImport, exportRunCSV, exportRunJSON, exportScenarioCSV, exportScenarioJSON, exportLibraryCSV, exportLibraryJSON,
    exportSessionJSON, PARAM_KEYS, GLOBAL_KEYS, MAX_STEPS, MAX_BYTES };
})();
if (typeof module !== 'undefined') module.exports = IO;
