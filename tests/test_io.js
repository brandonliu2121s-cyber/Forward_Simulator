// Tests for dashboard/io.js. Run via tests/test_dashboard_io.py (needs Node) or:  node tests/test_io.js <data.json>
const assert = require('assert');
const fs = require('fs');
const IO = require('../dashboard/io.js');
const Engine = require('../dashboard/engine.js');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const Z = data.scenario.zs, A = data.scenario.actions, LIB = data.instruments;
let n = 0, failed = 0;
const t = (name, fn) => { n++; try { fn(); } catch (e) { failed++; console.log('FAIL', name, '\n   ', e.message.split('\n')[0]); } };
const close = (a, b, m) => assert.ok(Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(b)), `${m}: ${a} vs ${b}`);

t('csv parser: quotes, escaped quotes, embedded newline, CRLF, BOM, blank lines', () => {
  const r = IO.parseCSV('﻿a,b,c\r\n1,"x, y","he said ""hi"""\r\n\r\n"multi\nline",2,3\r\n');
  assert.deepStrictEqual(r, [['a', 'b', 'c'], ['1', 'x, y', 'he said "hi"'], ['multi\nline', '2', '3']]);
});
t('csv parser: semicolon and tab delimiters', () => {
  assert.deepStrictEqual(IO.parseCSV('a;b\n1;2'), [['a', 'b'], ['1', '2']]);
  assert.deepStrictEqual(IO.parseCSV('a\tb\n1\t2'), [['a', 'b'], ['1', '2']]);
});
t('csv writer guards formula injection and quotes specials', () => {
  const s = IO.toCSV(['n'], [['=cmd()'], ['a,b'], ['-5x'], [-3], [-0]]);
  assert.ok(s.includes("'=cmd()") && s.includes('"a,b"') && s.includes("'-5x") && s.includes('\r\n-3\r\n') && s.includes('\r\n0\r\n'));
});

t('scenario CSV round-trip', () => {
  const r = IO.parseImport(IO.exportScenarioCSV(Z, A));
  assert.strictEqual(r.kind, 'scenario'); assert.deepStrictEqual(r.errors, []);
  assert.deepStrictEqual(r.zs, Z); assert.deepStrictEqual(r.acts, A);
});
t('scenario JSON round-trip (and via session scenario object)', () => {
  const r = IO.parseImport(IO.exportScenarioJSON({ seed: 277, note: 'x', zs: Z, acts: A }));
  assert.strictEqual(r.kind, 'scenario'); assert.deepStrictEqual(r.zs, Z); assert.deepStrictEqual(r.acts, A);
});
t('scenario JSON forms: steps array, rows array, bare moves/actions', () => {
  const steps = [{ move_sigma: 1.5, action: 'buy' }, { z: -0.5, action: 'SELL' }, { move: 0, client_action: 'none' }];
  for (const txt of [JSON.stringify(steps), JSON.stringify({ steps }), JSON.stringify({ moves: [1.5, -0.5, 0], actions: ['BUY', 'SELL', 'NONE'] })]) {
    const r = IO.parseImport(txt); assert.strictEqual(r.kind, 'scenario', txt); assert.deepStrictEqual(r.acts, ['BUY', 'SELL', 'NONE']);
  }
});
t('Excel-pasted scenario columns (A:C of the Simulation sheet) import', () => {
  const r = IO.parseImport('Step,"Market move\n(sigma units)","Client action\n(BUY / SELL / NONE)"\n1,1.8,NONE\n2,-1.3,BUY\n3,-0.4,SELL\n');
  assert.strictEqual(r.kind, 'scenario'); assert.deepStrictEqual(r.zs, [1.8, -1.3, -0.4]); assert.deepStrictEqual(r.acts, ['NONE', 'BUY', 'SELL']);
});
t('action shorthand and blanks', () => {
  const r = IO.parseImport('move,action\n1,b\n2,S\n3,\n4,-\n5,N');
  assert.deepStrictEqual(r.acts, ['BUY', 'SELL', 'NONE', 'NONE', 'NONE']);
});
t('exported run CSV re-imports as the same scenario, and re-simulates identically', () => {
  const p = Object.assign({}, LIB[0].params, data.globals);
  const rows = Engine.simulate(Z, A, p);
  const r = IO.parseImport(IO.exportRunCSV(rows));
  assert.strictEqual(r.kind, 'scenario'); assert.deepStrictEqual(r.zs, Z); assert.deepStrictEqual(r.acts, A);
  const again = Engine.simulate(r.zs, r.acts, p);
  again.forEach((x, i) => close(x.cum, rows[i].cum, 'cum step ' + (i + 1)));
});
t('run CSV/JSON content', () => {
  const p = Object.assign({}, LIB[0].params, data.globals), rows = Engine.simulate(Z, A, p);
  const parsed = IO.parseCSV(IO.exportRunCSV(rows));
  assert.strictEqual(parsed.length, rows.length + 1); assert.strictEqual(parsed[0][0], 'step');
  const j = JSON.parse(IO.exportRunJSON({ instrument: 'USD/SGD', unit: 'USD', pnl: 'SGD', params: p, globals: data.globals, summary: Engine.summarize(rows, p) }, rows));
  assert.strictEqual(j.steps.length, rows.length); assert.strictEqual(j.format, 'forward-desk-run');
  close(j.steps[rows.length - 1].cum_pnl, rows[rows.length - 1].cum, 'last cum');
});

t('library CSV round-trip for EVERY instrument (including Brent Crude)', () => {
  assert.ok(LIB.some((i) => i.name === 'Brent Crude'), 'Brent present in library');
  const r = IO.parseImport(IO.exportLibraryCSV(LIB));
  assert.strictEqual(r.kind, 'library'); assert.deepStrictEqual(r.errors, []); assert.strictEqual(r.instruments.length, LIB.length);
  LIB.forEach((i, k) => {
    const g = r.instruments[k]; assert.strictEqual(g.name, i.name); assert.strictEqual(g.type, i.type); assert.strictEqual(g.unit, i.unit); assert.strictEqual(g.pnl, i.pnl);
    for (const key of IO.PARAM_KEYS) close(g.params[key], i.params[key], i.name + '.' + key);
  });
});
t('library JSON round-trip, flat and nested forms', () => {
  const r = IO.parseImport(IO.exportLibraryJSON(LIB));
  assert.strictEqual(r.kind, 'library'); assert.strictEqual(r.instruments.length, LIB.length);
  const nested = IO.parseImport(JSON.stringify({ instruments: LIB }));   // internal shape with params{}
  assert.strictEqual(nested.kind, 'library'); assert.deepStrictEqual(nested.errors, []); close(nested.instruments[0].params.rate_a, LIB[0].params.rate_a, 'nested rate_a');
  const bare = IO.parseImport(JSON.stringify(LIB.slice(0, 2)));          // bare array
  assert.strictEqual(bare.kind, 'library'); assert.strictEqual(bare.instruments.length, 2);
});
t('Excel "Instruments" sheet exported to CSV imports (percent strings, n/a, computed columns)', () => {
  const head = 'Instrument,Type,Position unit,P&L ccy,Spot,Rate A,Financing (commodity),Storage (commodity),Rate B,Day basis A,Day basis B,Tenor (days),Tick size,Quote size (units),Spread (ticks),Max skew (ticks),Position limit (units),Loss limit (P&L ccy),Hedge cost (ticks),Step vol (ticks),Fair forward,Fwd points (ticks),Premium / (discount) p.a.,Source / note';
  const fx = 'USD/SGD,FX,USD,SGD,1.2850,4.00%,n/a,n/a,0.55%,360,365,45,0.0001,"250,000",5.0,3.0,"1,000,000","1,800",1.0,3.0,1.2795,(55.3),(3.49%),Original brief';
  const cm = 'Brent Crude,Commodity,bbl,USD,69.0000,7.00%,4.00%,2.00%,6.00%,365,365,90,0.0100,"10,000",4.0,3.0,"40,000","19,200",1.0,8.0,68.83,(168),(1.0%),ICE Brent';
  const r = IO.parseImport([head, fx, cm].join('\n'));
  assert.strictEqual(r.kind, 'library'); assert.deepStrictEqual(r.errors, []);
  close(r.instruments[0].params.rate_a, 0.04, 'rate_a'); close(r.instruments[0].params.rate_b, 0.0055, 'rate_b');
  close(r.instruments[0].params.clip, 250000, 'clip'); close(r.instruments[1].params.loss_limit, 19200, 'loss');
  assert.strictEqual(r.instruments[1].type, 'Commodity');
});
t('session JSON round-trip with overrides, globals and an embedded instrument definition', () => {
  const inst = LIB[0], p = Object.assign({}, inst.params, data.globals), rows = Engine.simulate(Z, A, p);
  const txt = IO.exportSessionJSON({ instrument: inst.name, definition: inst, overrides: { spread_ticks: 8 }, globals: { hedge_target_pct: 0.25, halt_on_loss: 0, start_pos: 0 },
    scenario: { seed: 277, note: 'Excel scenario', zs: Z, acts: A }, summary: Engine.summarize(rows, p), rows });
  const r = IO.parseImport(txt);
  assert.strictEqual(r.kind, 'session'); assert.deepStrictEqual(r.errors, []);
  assert.strictEqual(r.instrument, 'USD/SGD'); assert.deepStrictEqual(r.overrides, { spread_ticks: 8 }); assert.strictEqual(r.globals.hedge_target_pct, 0.25);
  assert.deepStrictEqual(r.scenario.zs, Z); assert.strictEqual(r.definition.name, 'USD/SGD'); assert.strictEqual(r.scenario.seed, 277);
});

t('session: embedded definition must match the instrument name', () => {
  const r = IO.parseImport(JSON.stringify({ format: 'forward-desk-session', instrument: 'Gold', instrument_definition: Object.assign({}, LIB[0], { params: undefined }, LIB[0].params, { name: 'USD/SGD' }) }));
  assert.ok(r.errors.some((e) => e.includes('instrument_definition is for')), JSON.stringify(r.errors));
});
t('errors: empty, bad JSON, unknown CSV, oversized', () => {
  assert.ok(IO.parseImport('   ').errors[0].includes('Nothing to import'));
  assert.ok(IO.parseImport('{"a":').errors[0].includes('not valid'));
  assert.ok(IO.parseImport('foo,bar\n1,2').errors[0].includes('recognise'));
  assert.ok(IO.parseImport('x'.repeat(IO.MAX_BYTES + 1)).errors[0].includes('2 MB'));
  assert.ok(IO.parseImport('{"hello":1}').errors[0].includes('Unrecognised JSON'));
});
t('errors: scenario row problems name the line', () => {
  const r = IO.parseImport('step,move,action\n1,0.5,BUY\n2,abc,SELL\n3,1,HOLD\n4,99,BUY');
  assert.strictEqual(r.errors.length, 3); assert.ok(r.errors[0].includes('Line 3') && r.errors[1].includes('Line 4') && r.errors[2].includes('Line 5'));
});
t('scenario longer than the cap is truncated with a warning', () => {
  const csv = 'move,action\n' + Array.from({ length: IO.MAX_STEPS + 20 }, () => '0.1,BUY').join('\n');
  const r = IO.parseImport(csv); assert.strictEqual(r.zs.length, IO.MAX_STEPS); assert.ok(r.warnings[0].includes('Only the first'));
});
t('library validation: missing field, negative tick, bad type, percent-looking rate, duplicates', () => {
  const base = IO.exportLibraryCSV(LIB.slice(0, 1)).trim().split('\r\n');
  const mk = (edit) => { const h = base[0].split(','), v = base[1].split(','); edit(h, v); return h.join(',') + '\n' + v.join(','); };
  const col = (h, k) => h.indexOf(k);
  assert.ok(IO.parseImport(mk((h, v) => { v[col(h, 'tick')] = '-0.1'; })).errors[0].includes('tick must be greater than 0'));
  assert.ok(IO.parseImport(mk((h, v) => { v[col(h, 'type')] = 'Bond'; })).errors[0].includes('type must be FX or Commodity'));
  assert.ok(IO.parseImport(mk((h, v) => { v[col(h, 'rate_a')] = '4'; })).errors[0].includes('rate_a'));
  assert.ok(IO.parseImport(mk((h, v) => { v[col(h, 'clip')] = ''; })).errors[0].includes('clip is missing'));
  const dup = IO.parseImport(base[0] + '\n' + base[1] + '\n' + base[1]); assert.strictEqual(dup.instruments.length, 1); assert.ok(dup.warnings[0].includes('more than once'));
});
t('library: invalid rows are reported but valid rows still load', () => {
  const lines = IO.exportLibraryCSV(LIB.slice(0, 2)).trim().split('\r\n'), h = lines[0].split(','), bad = lines[2].split(',');
  bad[h.indexOf('spot')] = 'oops';
  const r = IO.parseImport([lines[0], lines[1], bad.join(',')].join('\n'));
  assert.strictEqual(r.instruments.length, 1); assert.strictEqual(r.errors.length, 1); assert.strictEqual(r.skipped, 1);
});
t('hostile input: prototype keys, reserved names, bad overrides, formula-looking names', () => {
  const evil = IO.parseImport('{"format":"forward-desk-session","instrument":"USD/SGD","overrides":{"__proto__":{"x":1},"constructor":5,"spread_ticks":"8","tick":0.01},"globals":{"halt_on_loss":7}}');
  assert.ok(evil.errors.length >= 2 && ({}).x === undefined);
  const r = IO.parseImport(JSON.stringify([{ name: '__proto__', type: 'FX', unit: 'USD', pnl: 'SGD' }, { name: '<img src=x onerror=alert(1)>', type: 'FX' }]));
  assert.strictEqual(r.instruments.length, 0); assert.ok(r.errors.length === 2);
  const fx = LIB[0];
  const lib = IO.parseImport(IO.exportLibraryCSV([Object.assign({}, fx, { name: '=HYPERLINK("http://evil")' })]));
  assert.ok(lib.instruments[0].name.startsWith('=HYPERLINK'), 'guard prefix stripped on re-import');
  assert.ok(IO.exportLibraryCSV([Object.assign({}, fx, { name: '=HYPERLINK("http://evil")' })]).includes("\"'=HYPERLINK"), 'guard applied on export');
});

// ---- Setup file (the Setup page's "Load setup from CSV")
t('setup csv: vertical setting,value rows fill params, globals, steps and instrument', () => {
  const r = IO.parseSetup('setting,value\r\ninstrument,EUR/USD\r\nspot,1.17\r\nspread_ticks,8\r\nrate_a,4%\r\nrate_b,0.0055\r\ntenor_days,30\r\nsteps,80\r\nhedge_target_pct,50%\r\nhalt_on_loss,no\r\nopening_position,250000\r\n');
  assert.strictEqual(r.kind, 'setup'); assert.deepStrictEqual(r.errors, []);
  assert.strictEqual(r.instrument, 'EUR/USD'); assert.strictEqual(r.steps, 80);
  assert.deepStrictEqual(r.overrides, { spot_init: 1.17, spread_ticks: 8, rate_a: 0.04, rate_b: 0.0055, tenor_days: 30 });
  assert.deepStrictEqual(r.globals, { hedge_target_pct: 0.5, halt_on_loss: 0, start_pos: 250000 });
});
t('setup csv: a header row with one data row, headers as written in the Excel sheet', () => {
  const r = IO.parseSetup('Instrument,Spot,Spread (ticks),Position limit (units),Tenor (days)\nUSD/SGD,1.3,6,2000000,60\n');
  assert.deepStrictEqual(r.overrides, { spot_init: 1.3, spread_ticks: 6, pos_limit: 2000000, tenor_days: 60 }); assert.strictEqual(r.instrument, 'USD/SGD');
});
t('setup csv: semicolon delimiter, quoted thousands, extra rows noted, blanks skipped', () => {
  const r = IO.parseSetup('setting;value\nclip;"250,000"\nloss_limit;\nspread_ticks;7\n');
  assert.deepStrictEqual(r.overrides, { clip: 250000, spread_ticks: 7 });
  const w = IO.parseSetup('spread_ticks,tick\n5,0.0001\n9,0.0002\n');
  assert.deepStrictEqual(w.overrides, { spread_ticks: 5, tick: 0.0001 }); assert.ok(w.warnings.some((x) => /only the first/.test(x)));
});
t('setup csv: rates mean what people write (4, 4%, 0.04, 0.55) and say when they guessed', () => {
  const r = IO.parseSetup('setting,value\nrate_a,4\nrate_b,0.55\n');
  assert.deepStrictEqual(r.overrides, { rate_a: 0.04, rate_b: 0.0055 }); assert.strictEqual(r.warnings.length, 2);
  const f = IO.parseSetup('setting,value\nrate_a,0.04\nrate_b,0.5%\n');
  assert.deepStrictEqual(f.overrides, { rate_a: 0.04, rate_b: 0.005 }); assert.strictEqual(f.warnings.length, 0);
  assert.strictEqual(IO.parseSetup('setting,value\nhedge_target_pct,0.25\n').globals.hedge_target_pct, 0.25);
  assert.strictEqual(IO.parseSetup('setting,value\nhedge_target_pct,25\n').globals.hedge_target_pct, 0.25);
});
t('setup csv: bad values are all reported and nothing is half-applied', () => {
  const r = IO.parseSetup('setting,value\nspread_ticks,abc\nrate_a,500\nsteps,5\ntenor_days,-3\nhalt_on_loss,maybe\nspot,0\nmax_skew_ticks,-1\n');
  assert.strictEqual(r.errors.length, 7);
  assert.ok(r.errors.some((x) => /steps/.test(x)) && r.errors.some((x) => /halt_on_loss/.test(x)));
});
t('setup csv: unknown columns are listed and ignored; a file with nothing usable fails clearly', () => {
  const r = IO.parseSetup('setting,value\nspread_ticks,7\nfavourite_colour,blue\n');
  assert.deepStrictEqual(r.overrides, { spread_ticks: 7 }); assert.ok(r.warnings.some((x) => /favourite_colour/.test(x)));
  assert.ok(IO.parseSetup('setting,value\nfavourite_colour,blue\n').errors.length === 1);
  assert.ok(IO.parseSetup('foo,bar\n1,2\n').errors[0].includes('Could not recognise'));
  assert.ok(IO.parseSetup('').errors.length && IO.parseSetup('x').errors.length);
});
t('setup csv: duplicates keep the last value and say so; formula-looking and oversized cells are harmless', () => {
  const r = IO.parseSetup('setting,value\nspread_ticks,5\nspread_ticks,9\ninstrument,"=HYPERLINK(""http://evil"")"\n');
  assert.strictEqual(r.overrides.spread_ticks, 9); assert.ok(r.warnings.some((x) => /more than once/.test(x)));
  assert.ok(r.instrument.startsWith('=HYPERLINK'));                                   // only ever matched against the library, never evaluated
  assert.ok(IO.parseSetup('a'.repeat(3 * 1024 * 1024)).errors[0].includes('2 MB'));
});
t('setup: flat JSON works, and sessions, scenarios and libraries still route to the normal importer', () => {
  const j = IO.parseSetup('{"instrument":"Gold","spread_ticks":6,"halt_on_loss":true,"steps":120}');
  assert.strictEqual(j.kind, 'setup'); assert.deepStrictEqual(j.overrides, { spread_ticks: 6 }); assert.strictEqual(j.globals.halt_on_loss, 1); assert.strictEqual(j.steps, 120);
  assert.strictEqual(IO.parseSetup(IO.exportScenarioCSV(Z.slice(0, 20), A.slice(0, 20))).kind, 'scenario');
  assert.strictEqual(IO.parseSetup(IO.exportLibraryCSV([LIB[0]])).kind, 'library');
  assert.strictEqual(IO.parseSetup(IO.exportScenarioJSON({ seed: 1, note: 'x', zs: Z.slice(0, 20), acts: A.slice(0, 20) })).kind, 'scenario');
  assert.ok(IO.parseSetup('{"a":').errors[0].includes('not valid'));
});
t('setup template round-trips: exportSetupCSV -> parseSetup gives back the same inputs', () => {
  const p = LIB[0].params, csv = IO.exportSetupCSV({ instrument: LIB[0].name, steps: 60, params: p, globals: { hedge_target_pct: 0.25, halt_on_loss: 1, start_pos: 0 } });
  const r = IO.parseSetup(csv);
  assert.deepStrictEqual(r.errors, []); assert.strictEqual(r.instrument, LIB[0].name); assert.strictEqual(r.steps, 60);
  for (const k of IO.PARAM_KEYS) close(r.overrides[k], p[k], k);
  assert.deepStrictEqual(r.globals, { hedge_target_pct: 0.25, halt_on_loss: 1, start_pos: 0 });
  assert.strictEqual(r.warnings.length, 0, r.warnings.join(' '));                        // fractions written by the template are not "guessed"
});
console.log(`${n - failed}/${n} io tests passed`);
process.exit(failed ? 1 : 0);
