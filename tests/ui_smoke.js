// UI smoke test for dashboard/index.html (needs Playwright + Chromium).  Run:  node tests/ui_smoke.js
// Exercises overrides, chart tabs, event chips, keyboard, bars, scenario buttons, activity edits, search, popovers and the pricing stepper.
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ ...(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {}) });
  const pg = await b.newPage({ viewport: { width: 1280, height: 900 } });
  const errs = []; pg.on('pageerror', (e) => errs.push(e.message)); pg.on('console', (m) => m.type() === 'error' && errs.push(m.text()));
  await pg.goto('file://'+require('path').resolve(__dirname,'../dashboard/index.html#desk')); await pg.waitForTimeout(400);
  const settled = (page) => page.waitForFunction(() => !document.documentElement.dataset.reveal, null, { timeout: 8000 });   // chart reveal + number count-up finished
  const txt = async (s) => { await settled(pg); return pg.locator(s).first().innerText(); };
  const ok = (name, cond) => console.log((cond ? 'PASS' : 'FAIL') + '  ' + name);
  const pnl0 = await txt('.left .big');
  // 1. Setup override: spread 5 -> 12 ticks changes P&L and shows override styling
  await pg.click('.nav button:has-text("Setup")');
  await pg.fill('#f-spread_ticks', '12'); await pg.dispatchEvent('#f-spread_ticks', 'change'); await pg.waitForTimeout(200);
  ok('override gets orange class', (await pg.getAttribute('#f-spread_ticks', 'class')) === 'ov');
  await pg.click('.nav button:has-text("Desk")'); await pg.waitForTimeout(200);
  ok('P&L changes after spread override', (await txt('.left .big')) !== pnl0);
  // 2. reset
  await pg.click('.nav button:has-text("Setup")'); await pg.click('button:has-text("Reset to defaults")');
  await pg.click('.nav button:has-text("Desk")'); await pg.waitForTimeout(150);
  ok('reset restores P&L', (await txt('.left .big')) === pnl0);
  // 3. range + metric
  await pg.click('.ranges button:has-text("20")'); await pg.click('.seg button:has-text("Position")'); await pg.waitForTimeout(150);
  ok('metric title switches', (await txt('#hero-title')).startsWith('Closing position'));
  ok('range tab pressed', (await pg.getAttribute('.ranges button:has-text("20")', 'aria-pressed')) === 'true');
  // 4. event chip pins the tooltip
  await pg.click('.seg button:has-text("P&L")'); await pg.click('.ranges button:has-text("All")');
  await pg.click('.evchip >> nth=0'); await pg.waitForTimeout(500);
  ok('chip pins tooltip on step 24', (await txt('#tip')).includes('Step 24'));
  // 5. keyboard on chart
  await pg.focus('#plot svg'); await pg.keyboard.press('ArrowLeft'); await pg.waitForTimeout(100);
  ok('arrow key moves pinned step', (await txt('#tip')).includes('Step 23'));
  // 6. bar mode + table view
  await pg.click('button[data-act="barmode"]'); ok('bar mode -> At end', (await txt('button[data-act="barmode"]')).includes('At end'));
  await pg.click('button[data-act="bartable"]'); ok('table view', (await pg.locator('.tbl-mini').count()) === 1);
  // 7. reshuffle changes scenario; Excel button restores
  await pg.click('button[data-act="reshuffle"]'); await pg.waitForTimeout(150);
  const shuffled = await txt('.left .big'); ok('reshuffle changes P&L', shuffled !== pnl0);
  await pg.click('.nav button:has-text("Activity")'); await pg.click('button:has-text("Load Excel scenario")');
  await pg.click('.nav button:has-text("Desk")'); await pg.waitForTimeout(150);
  ok('Excel scenario restores P&L', (await txt('.left .big')) === pnl0);
  // 8. Activity: cycle an action, edit a move
  await pg.click('.nav button:has-text("Activity")');
  const before = await pg.locator('tbody tr').nth(0).locator('.actbtn').innerText();
  await pg.locator('tbody tr').nth(0).locator('.actbtn').click(); await pg.waitForTimeout(100);
  ok('action cycles', (await pg.locator('tbody tr').nth(0).locator('.actbtn').innerText()) !== before);
  // 9. instrument search + select
  await pg.click('button[aria-label="Search instruments"]'); await pg.keyboard.type('crude'); await pg.waitForTimeout(150);
  ok('search filters to the two crude oils (WTI and Brent)', (await pg.locator('tbody tr').count()) === 2);
  await pg.keyboard.press('Control+a'); await pg.keyboard.type('wti'); await pg.waitForTimeout(150);
  ok('search narrows to 1 row', (await pg.locator('tbody tr').count()) === 1);
  await pg.click('tbody tr'); await pg.waitForTimeout(250);
  ok('row click loads WTI on desk', (await txt('.who')).includes('WTI Crude') && (await txt('h2')).includes('Desk Performance'));
  // 10. bell popover + escape
  await pg.click('button[aria-label="Limit alerts"]'); ok('bell popover opens', (await pg.locator('.pop').count()) === 1);
  await pg.keyboard.press('Escape'); ok('Escape closes popover', (await pg.locator('.pop').count()) === 0);
  // 11. pricing stepper
  await pg.click('.nav button:has-text("Pricing")'); await pg.click('button[aria-label="One clip longer"]'); await pg.click('button[aria-label="One clip longer"]');
  ok('stepper to +4 clips (limit) then hedge warning', (await txt('#clipval')).includes('4') && (await pg.locator('main').innerText()).includes('can breach'));
  // ---------- import / export + Brent ----------
  const fs = require('fs'), os = require('os'), path = require('path');
  await pg.click('.nav button:has-text("Desk")');
  await pg.click('.who'); ok('Brent Crude is in the instrument menu', (await pg.locator('.pop .item:has-text("Brent Crude")').count()) === 1);
  await pg.click('.pop .item:has-text("Brent Crude")'); await pg.waitForTimeout(200);
  ok('Brent loads on the desk', (await txt('.who')).includes('Brent Crude') && (await pg.locator('.wl-item:has-text("Brent Crude")').count()) === 1);
  await pg.click('.who'); await pg.click('.pop .item:has-text("USD/SGD")'); await pg.waitForTimeout(200);
  const base = await txt('.left .big');
  await pg.click('button[aria-label="Import or export data"]'); await pg.waitForTimeout(150);
  ok('dialog opens on Export with run CSV', (await pg.inputValue('#exp-text')).startsWith('step,move_sigma,action,spot,fair_forward'));
  ok('CSV has one line per step plus header', (await pg.inputValue('#exp-text')).trim().split('\n').length === 61);
  const [dl] = await Promise.all([pg.waitForEvent('download'), pg.click('button[data-act="dlgdl"]')]);
  ok('download file name', dl.suggestedFilename() === 'forward-desk_usd-sgd_run.csv');
  const dlText = fs.readFileSync(await dl.path(), 'utf8'); ok('downloaded content matches the box (file keeps CRLF line endings)', dlText.includes('\r\n') && dlText.replace(/\r\n/g, '\n') === (await pg.inputValue('#exp-text')));
  await pg.click('button[data-act="dlgcopy"]'); await pg.waitForTimeout(150);
  ok('copy gives feedback (copied or selected)', /Copied|Text selected/.test(await txt('#toast')));
  await pg.click('button[data-act="dlgwhat"][data-k="scenario"]'); await pg.click('button[data-act="dlgfmt"][data-k="json"]');
  const sj = JSON.parse(await pg.inputValue('#exp-text')); ok('scenario JSON has 60 moves/actions', sj.moves.length === 60 && sj.actions.length === 60);
  await pg.click('button[data-act="dlgwhat"][data-k="session"]'); ok('session forces JSON', JSON.parse(await pg.inputValue('#exp-text')).format === 'forward-desk-session' && (await pg.getAttribute('button[data-act="dlgfmt"][data-k="csv"]', 'disabled')) !== null);
  const sessionText = await pg.inputValue('#exp-text');
  // import: pasted scenario
  await pg.click('button[data-act="dlgtab"][data-k="import"]');
  const sc = 'step,move_sigma,action\n' + Array.from({ length: 12 }, (_, i) => `${i + 1},${i % 2 ? -1.5 : 2.5},${['BUY', 'SELL', 'NONE'][i % 3]}`).join('\n');
  await pg.fill('#imp-text', sc); await pg.waitForTimeout(150);
  ok('preview describes scenario', (await txt('#imp-prev')).includes('Scenario with 12 steps'));
  await pg.click('button[data-act="dlgapply"]'); await pg.waitForTimeout(300);
  ok('dialog closes and toast confirms', (await pg.locator('.dlg').count()) === 0 && (await txt('#toast')).includes('Scenario loaded: 12 steps'));
  ok('imported scenario changes the result', (await txt('.left .big')) !== base);
  // import: file upload of the session exported earlier restores the original scenario
  const tmp = path.join(os.tmpdir(), 'fd-session.json'); fs.writeFileSync(tmp, sessionText);
  await pg.click('button[aria-label="Import or export data"]'); await pg.click('button[data-act="dlgtab"][data-k="import"]');
  await pg.setInputFiles('#imp-file', tmp); await pg.waitForTimeout(300);
  ok('preview describes session', (await txt('#imp-prev')).includes('Session for USD/SGD'));
  await pg.click('button[data-act="dlgapply"]'); await pg.waitForTimeout(300);
  ok('session import restores the original P&L', (await txt('.left .big')) === base);
  // import: invalid text shows errors and no Apply button
  await pg.click('button[aria-label="Import or export data"]'); await pg.click('button[data-act="dlgtab"][data-k="import"]');
  await pg.fill('#imp-text', 'step,move,action\n1,oops,BUY\n2,1,HOLD'); await pg.waitForTimeout(150);
  ok('bad scenario shows row errors, no apply', (await txt('#imp-prev')).includes('Line 2') && (await pg.locator('button[data-act="dlgapply"]').count()) === 0);
  await pg.fill('#imp-text', '{"nope":'); await pg.waitForTimeout(100);
  ok('bad JSON explained', (await txt('#imp-prev')).includes('not valid'));
  // import: instrument library (example row), then restore
  await pg.click('button[data-act="dlgexample"][data-k="library"]'); await pg.waitForTimeout(150);
  ok('library preview', (await txt('#imp-prev')).includes('1 valid instrument'));
  await pg.click('button[data-act="dlgapply"]'); await pg.waitForTimeout(300);
  await pg.click('.nav button:has-text("Instruments")'); ok('Example Corn listed', (await pg.locator('tbody tr:has-text("Example Corn")').count()) === 1);
  await pg.click('tbody tr:has-text("Example Corn")'); await pg.waitForTimeout(250);
  ok('imported instrument runs on the desk', (await txt('.who')).includes('Example Corn') && (await pg.locator('.hero').count()) === 1);
  await pg.click('button[aria-label="Import or export data"]'); await pg.click('button[data-act="dlgtab"][data-k="import"]');
  await pg.click('button[data-act="dlgreset"]'); await pg.waitForTimeout(250);
  ok('restore removes the imported instrument and returns to default', (await txt('.who')).includes('USD/SGD'));
  await pg.keyboard.press('Escape'); ok('Escape closes the dialog', (await pg.locator('.dlg').count()) === 0);
  // ---------- downloads capability path (as inside the Claude artifact viewer) ----------
  const pc = await b.newPage({ viewport: { width: 1100, height: 800 } });
  await pc.addInitScript(() => { window.__saves = []; window.claude = { use: async (n) => (n === 'downloads' ? { save: async (r) => { window.__saves.push(r); return { status: 'saved' }; } } : null) }; });
  await pc.goto('file://' + require('path').resolve(__dirname, '../dashboard/index.html#desk')); await pc.waitForTimeout(300);
  await pc.click('button[aria-label="Import or export data"]'); await pc.click('button[data-act="dlgdl"]'); await pc.waitForTimeout(200);
  const saves = await pc.evaluate(() => window.__saves);
  ok('download goes through the downloads capability when present', saves.length === 1 && saves[0].filename === 'forward-desk_usd-sgd_run.csv' && saves[0].data.startsWith('step,move_sigma'));
  const pd = await b.newPage({ viewport: { width: 1100, height: 800 } });
  await pd.addInitScript(() => { window.claude = { use: async () => null }; });
  await pd.goto('file://' + require('path').resolve(__dirname, '../dashboard/index.html#desk')); await pd.waitForTimeout(300);
  await pd.click('button[aria-label="Import or export data"]');
  const [dl2] = await Promise.all([pd.waitForEvent('download', { timeout: 5000 }).catch(() => null), pd.click('button[data-act="dlgdl"]')]);
  ok('falls back to a browser download when the capability is unavailable', !!dl2 && dl2.suggestedFilename() === 'forward-desk_usd-sgd_run.csv');
  // ---------- motion (Emil Kowalski's rules) ----------
  const scaleOf = (el) => el.evaluate((n) => { const m = getComputedStyle(n).transform; return m === 'none' ? 1 : parseFloat(m.slice(7)); });
  const fresh = await b.newPage({ viewport: { width: 1280, height: 900 } });
  await fresh.addInitScript(() => { window.__t = []; });
  await fresh.goto('file://' + require('path').resolve(__dirname, '../dashboard/index.html#desk')); await fresh.waitForTimeout(150);
  ok('first load: cards settle in (main.enter present)', (await fresh.locator('main.enter').count()) === 1);
  await fresh.waitForTimeout(500);
  await fresh.click('.nav button:has-text("Pricing")'); await fresh.waitForTimeout(100);
  ok('view switching is NOT animated (core navigation)', (await fresh.locator('main.enter').count()) === 0);
  await fresh.click('.nav button:has-text("Desk")');
  // press feedback: scale(0.97) while held, back to 1 on release, and a 160ms ease-out transition (not 'all')
  const pill = fresh.locator('.pill:has-text("Filters")');
  const bx = await pill.boundingBox(); await fresh.mouse.move(bx.x + bx.width / 2, bx.y + bx.height / 2); await fresh.mouse.down(); await fresh.waitForTimeout(260);
  const held = await scaleOf(pill); await fresh.mouse.up(); await fresh.waitForTimeout(260);
  ok('press feedback scales to 0.97 and releases', Math.abs(held - 0.97) < 0.005 && Math.abs((await scaleOf(pill)) - 1) < 0.005);
  ok('buttons transition specific properties, never "all"', !(await pill.evaluate((n) => getComputedStyle(n).transitionProperty)).includes('all'));
  // popover: mouse opens with the entrance (origin-aware); keyboard opens with none
  await fresh.click('.who'); ok('popover opened by mouse animates in (.fresh)', (await fresh.locator('.pop.fresh').count()) === 1);
  await fresh.keyboard.press('Escape');
  await fresh.focus('.who'); await fresh.keyboard.press('Enter'); await fresh.waitForTimeout(80);
  ok('popover opened by keyboard does not animate', (await fresh.locator('.pop').count()) === 1 && (await fresh.locator('.pop.fresh').count()) === 0);
  await fresh.keyboard.press('Escape');
  // dialog: mouse open = entrance, mouse close = 140ms exit (.out then removed); Escape = instant
  await fresh.click('button[aria-label="Import or export data"]'); ok('dialog opened by mouse animates in', (await fresh.locator('.backdrop.fresh').count()) === 1);
  await fresh.waitForTimeout(260);
  await fresh.click('button[aria-label="Close"]'); await fresh.waitForTimeout(40);
  ok('mouse close plays a short exit first (.out)', (await fresh.locator('.backdrop.out').count()) === 1);
  await fresh.waitForTimeout(260); ok('...then the dialog is gone', (await fresh.locator('.dlg').count()) === 0);
  await fresh.click('button[aria-label="Import or export data"]'); await fresh.waitForTimeout(260);
  await fresh.keyboard.press('Escape'); ok('Escape closes instantly with no exit animation', (await fresh.locator('.dlg').count()) === 0);
  await fresh.focus('button[aria-label="Import or export data"]'); await fresh.keyboard.press('Enter'); await fresh.waitForTimeout(60);
  ok('dialog opened by keyboard does not animate', (await fresh.locator('.dlg').count()) === 1 && (await fresh.locator('.backdrop.fresh').count()) === 0);
  await fresh.keyboard.press('Escape');
  // toast leaves by the edge it came from, then is removed
  await fresh.click('button[aria-label="Import or export data"]'); await fresh.click('button[data-act="dlgcopy"]'); await fresh.waitForTimeout(300);
  ok('toast enters (visible)', !(await fresh.locator('#toast').evaluate((n) => n.hidden)));
  await fresh.waitForTimeout(5000); ok('toast plays its exit (.out) before hiding', (await fresh.locator('#toast.out').count()) === 1 || (await fresh.locator('#toast').evaluate((n) => n.hidden)));
  await fresh.waitForTimeout(400); ok('toast is hidden afterwards', await fresh.locator('#toast').evaluate((n) => n.hidden));
  // the transitions really run (not just classes): sample computed opacity frame by frame
  const sample = (pg, sel, ms) => pg.evaluate(([q, t]) => new Promise((res) => { const out = []; const iv = setInterval(() => { const n = document.querySelector(q); if (n) out.push(+getComputedStyle(n).opacity); }, 16); setTimeout(() => { clearInterval(iv); res(out); }, t); }), [sel, ms]);
  const intro = await b.newPage({ viewport: { width: 1280, height: 900 } });
  await intro.addInitScript(() => { window.__ops = []; const iv = setInterval(() => { const n = document.querySelector('main > :first-child'); if (n) window.__ops.push(+getComputedStyle(n).opacity); }, 16); setTimeout(() => clearInterval(iv), 900); });
  await intro.goto('file://' + require('path').resolve(__dirname, '../dashboard/index.html#desk')); await intro.waitForTimeout(1000);
  const ops = await intro.evaluate(() => window.__ops);
  ok('first-load stagger actually runs: card fades 0 -> 1 over the first frames', Math.min(...ops) < 0.9 && ops[ops.length - 1] === 1);
  await fresh.keyboard.press('Escape');   // the toast test above left the dialog open
  // selecting a nav tab with the pointer: the new pill starts lower/smaller and pushes up to rest
  await fresh.evaluate(() => { window.__tf = []; const iv = setInterval(() => { const n = document.querySelector('.nav button[aria-current="page"]'); if (n) window.__tf.push(getComputedStyle(n).transform); }, 16); setTimeout(() => clearInterval(iv), 450); });
  await fresh.click('.nav button:not([aria-current])'); await fresh.waitForTimeout(500);
  const tf = await fresh.evaluate(() => window.__tf);
  ok('tab select (pointer): pill starts displaced (translateY > 0) and settles at rest', tf.some((t) => t !== 'none' && /matrix\(([^)]*)\)/.test(t) && +t.match(/matrix\(([^)]*)\)/)[1].split(',')[5] > 1) && (tf[tf.length - 1] === 'none' || tf[tf.length - 1] === 'matrix(1, 0, 0, 1, 0, 0)'));
  await fresh.focus('.nav button:not([aria-current])'); const navBefore = await fresh.evaluate(() => document.querySelector('.nav button[aria-current="page"]').textContent);
  await fresh.keyboard.press('Enter'); await fresh.waitForTimeout(30);
  ok('tab select (keyboard): no rise class, instant', (await fresh.locator('.nav button.rise').count()) === 0 && (await fresh.evaluate(() => document.querySelector('.nav button[aria-current="page"]').textContent)) !== navBefore);
  const sp = sample(fresh, '.dlg', 450); await fresh.click('button[aria-label="Import or export data"]'); const dop = await sp;
  ok('dialog entrance actually runs: opacity rises from below 1 to exactly 1 within 300ms', Math.min(...dop) < 0.95 && dop[dop.length - 1] === 1);
  await fresh.keyboard.press('Escape');
  // reduced motion: gentler, not zero. Press movement is removed.
  const rm = await b.newContext({ reducedMotion: 'reduce', viewport: { width: 1280, height: 900 } }); const rp = await rm.newPage();
  await rp.goto('file://' + require('path').resolve(__dirname, '../dashboard/index.html#desk')); await rp.waitForTimeout(300);
  const rpill = rp.locator('.pill:has-text("Filters")'); const rb = await rpill.boundingBox(); await rp.mouse.move(rb.x + rb.width / 2, rb.y + rb.height / 2); await rp.mouse.down(); await rp.waitForTimeout(260);
  ok('reduced motion: no press scaling', Math.abs((await scaleOf(rpill)) - 1) < 0.005); await rp.mouse.up();
  // hover is gated: in a touch context no hover rule applies
  const touch = await b.newContext({ hasTouch: true, isMobile: true, viewport: { width: 400, height: 860 } }); const tp = await touch.newPage();
  await tp.goto('file://' + require('path').resolve(__dirname, '../dashboard/index.html#desk')); await tp.waitForTimeout(300);
  ok('touch device: (hover: hover) is false so hover styles are inert', !(await tp.evaluate(() => matchMedia('(hover: hover) and (pointer: fine)').matches)));
  // front page: inputs first, results only after Run
  const fp = await b.newPage({ viewport: { width: 1280, height: 900 } }); const ferrs = []; fp.on('pageerror', (e) => ferrs.push(String(e)));
  await fp.goto('file://' + require('path').resolve(__dirname, '../dashboard/index.html')); await fp.waitForTimeout(300);
  ok('opens on Setup with the inputs and a Run button', (await fp.locator('.nav button[aria-current="page"]').innerText()) === 'Setup' && (await fp.locator('#f-spread_ticks').count()) === 1 && (await fp.locator('button.run').count()) >= 1);
  ok('Setup is the first tab', (await fp.locator('.nav button').first().innerText()) === 'Setup');
  ok('no chart or advice before Run', (await fp.locator('#plot').count()) === 0 && (await fp.locator('.insight').count()) === 0);
  await fp.click('.nav button:has-text("Pricing")'); await fp.waitForTimeout(100);
  ok('result tabs show a gate until Run', (await fp.locator('.gate').count()) === 1 && (await fp.locator('table.recipe').count()) === 0);
  await fp.click('.gate button'); await fp.waitForTimeout(100);
  // edit a field then click Run straight away: the field must not swallow the click
  await fp.fill('#f-spread_ticks', '9'); await fp.click('button.run >> nth=0'); await fp.waitForTimeout(500);
  ok('one click on Run (straight from a field) opens the Desk with chart and advice', (await fp.locator('.nav button[aria-current="page"]').innerText()) === 'Desk' && (await fp.locator('#plot').count()) === 1 && (await fp.locator('.insight').count()) >= 1);
  await fp.click('.nav button:has-text("Setup")'); ok('the entered input was kept', (await fp.inputValue('#f-spread_ticks')) === '9');
  ok('after a run the button reads Update results', (await fp.locator('button.run').first().innerText()) === 'Update results');
  ok('front page: no page errors', ferrs.length === 0);
  // chart reveal: the visuals build up slowly after Run and whenever the inputs change, then settle on the exact final values
  const rv = await b.newPage({ viewport: { width: 1280, height: 900 } }); const rerrs = []; rv.on('pageerror', (e) => rerrs.push(String(e)));
  await rv.goto('file://' + require('path').resolve(__dirname, '../dashboard/index.html')); await rv.waitForTimeout(250);
  await rv.click('button.run >> nth=0'); await rv.waitForTimeout(350);
  const mid = await rv.evaluate(() => ({ series: document.querySelector('#series').getAnimations().length, clip: getComputedStyle(document.querySelector('#series')).clipPath, pnl: document.querySelector('.left .big').textContent, bars: document.querySelectorAll('.bar .fill').length && document.querySelector('.bar .fill').getAnimations().length }));
  ok('line chart is mid-reveal 350ms after Run (clip-path animating)', mid.series >= 1 && mid.clip !== 'none');
  ok('limit-usage bars animate', mid.bars >= 1);
  await settled(rv); const fin = await rv.evaluate(() => ({ pnl: document.querySelector('.left .big').textContent, clip: getComputedStyle(document.querySelector('#series')).clipPath, anim: document.getAnimations().length }));
  ok('numbers count up and land on the exact final value', mid.pnl !== fin.pnl && /1,928\.13/.test(fin.pnl));
  ok('everything is cleaned up afterwards (no lingering clip or animations)', fin.clip === 'none' && fin.anim === 0);
  await rv.click('.pill:has-text("Peak")'); await rv.waitForTimeout(200);
  ok('toggling a view option does not replay the reveal', (await rv.evaluate(() => document.documentElement.dataset.reveal)) === undefined);
  await rv.click('button[aria-label="New random scenario"]'); await rv.waitForTimeout(300);
  ok('new scenario replays the reveal', (await rv.evaluate(() => document.querySelector('#series').getAnimations().length)) >= 1);
  await settled(rv);
  const rr = await b.newContext({ reducedMotion: 'reduce', viewport: { width: 1280, height: 900 } }); const rrp = await rr.newPage();
  await rrp.goto('file://' + require('path').resolve(__dirname, '../dashboard/index.html')); await rrp.waitForTimeout(250);
  await rrp.click('button.run >> nth=0'); await rrp.waitForTimeout(120);
  ok('reduced motion: no wipe or count-up, numbers are exact straight away', (await rrp.evaluate(() => getComputedStyle(document.querySelector('#series')).clipPath)) === 'none' && /1,928\.13/.test(await rrp.locator('.left .big').innerText()));
  ok('reveal: no page errors', rerrs.length === 0);
  // ---- Saved runs (Supabase) against a mocked backend: build a page that has a config, intercept its network calls
  {
    const cp = require('child_process'), os = require('os'), fs = require('fs'), path = require('path');
    const BASE = 'https://abcdefghij.supabase.co', root = path.resolve(__dirname, '..');
    const tmp = path.join(os.tmpdir(), 'forward_desk_cloud_test.html');
    cp.execFileSync('python3', ['-c', `import sys; sys.path.insert(0,'dev'); sys.path.insert(0,'python'); import build_dashboard as b; open(${JSON.stringify(tmp)},'w').write(b.standalone(b.fragment()))`],
      { cwd: root, env: Object.assign({}, process.env, { SUPABASE_URL: BASE, SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_test' }) });
    const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
    const token = `${b64({ alg: 'HS256' })}.${b64({ sub: '11111111-2222-4333-8444-555555555555', email: 'me@example.com', exp: Math.floor(Date.now() / 1000) + 3600 })}.sig`;
    const cctx = await b.newContext({ viewport: { width: 1280, height: 900 } }); const cpg = await cctx.newPage(); const cerrs = []; cpg.on('pageerror', (e) => cerrs.push(String(e)));
    const db = { runs: [], otp: 0, authHeaders: [] };
    await cctx.route(BASE + '/**', async (route) => {
      const req = route.request(), u = new URL(req.url()), m = req.method(), body = req.postData() ? JSON.parse(req.postData()) : null;
      const json = (status, o) => route.fulfill({ status, contentType: 'application/json', headers: { 'access-control-allow-origin': '*' }, body: o === undefined ? '' : JSON.stringify(o) });
      if (m === 'OPTIONS') return route.fulfill({ status: 204, headers: { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*' } });
      db.authHeaders.push(req.headers().authorization);
      if (u.pathname === '/auth/v1/otp') { db.otp++; return json(200, {}); }
      if (u.pathname === '/auth/v1/logout') return json(204);
      if (u.pathname === '/rest/v1/runs') {
        const id = u.searchParams.get('id');
        if (m === 'GET') return json(200, id ? db.runs.filter((r) => 'eq.' + r.id === id) : db.runs);
        if (m === 'POST') { const r = Object.assign({ id: '99999999-0000-4000-8000-' + String(db.runs.length).padStart(12, '0'), created_at: new Date().toISOString() }, body); db.runs.unshift(r); return json(201, [r]); }
        if (m === 'DELETE') { const gone = db.runs.filter((r) => 'eq.' + r.id === id); db.runs = db.runs.filter((r) => !gone.includes(r)); return json(200, gone); }
      }
      return json(404, { message: 'no route' });
    });
    await cpg.goto('file://' + tmp); await cpg.waitForTimeout(300);
    ok('saved-runs card is offered when a config is built in', (await cpg.locator('.cloud').count()) === 1 && (await cpg.locator('#cl-email').count()) === 1);
    ok('static build has no saved-runs card', (await fp.locator('.cloud').count()) === 0);
    await cpg.fill('#cl-email', 'me@example.com'); await cpg.press('#cl-email', 'Enter'); await cpg.waitForTimeout(300);
    ok('emailing a sign-in link posts the otp request and tells the user', db.otp === 1 && /inbox/i.test(await cpg.locator('.cloud .note').innerText()));
    await cpg.goto('file://' + tmp + '#access_token=' + token + '&refresh_token=rt&expires_in=3600&token_type=bearer&type=magiclink'); await cpg.waitForTimeout(500);
    ok('magic-link return signs in and clears the tokens from the address bar', (await cpg.locator('.cloud .mail').innerText()) === 'me@example.com' && !/access_token/.test(cpg.url()));
    ok('empty state for a new user', /Nothing saved yet/.test(await cpg.locator('.cloud').innerText()));
    await cpg.fill('#f-spread_ticks', '9'); await cpg.fill('#cl-name', 'Wide spread'); await cpg.click('button[data-act="cloudsave"]'); await cpg.waitForTimeout(400);
    ok('saving lists the run with its instrument', /Wide spread/.test(await cpg.locator('.runs').innerText()) && /USD\/SGD/.test(await cpg.locator('.runs').innerText()));
    ok('stored session keeps the override and drops the bulky step rows', db.runs.length === 1 && db.runs[0].session.overrides.spread_ticks === 9 && !('steps' in db.runs[0].session));
    ok('requests used the user token, not the publishable key', db.authHeaders.filter((h) => h && h.includes(token)).length >= 2);
    await cpg.reload(); await cpg.waitForTimeout(500);
    ok('after a reload the session persists and the run is listed', /Wide spread/.test(await cpg.locator('.runs').innerText()));
    await cpg.click('button[data-act="resetover"]'); ok('inputs reset', (await cpg.inputValue('#f-spread_ticks')) === '');
    await cpg.click('button[data-act="cloudload"]'); await cpg.waitForTimeout(400);
    ok('loading restores the saved input', (await cpg.inputValue('#f-spread_ticks')) === '9' && /Loaded/.test(await cpg.locator('.cloud .note').innerText()));
    await cpg.click('button[data-act="clouddel"]'); ok('first delete click only asks to confirm', db.runs.length === 1 && /Confirm/.test(await cpg.locator('button[data-act="clouddel"]').innerText()));
    await cpg.click('button[data-act="clouddel"]'); await cpg.waitForTimeout(400);
    ok('second click deletes', db.runs.length === 0 && /Nothing saved yet/.test(await cpg.locator('.cloud').innerText()));
    await cpg.click('button[data-act="cloudout"]'); await cpg.waitForTimeout(300);
    ok('sign out returns to the sign-in form', (await cpg.locator('#cl-email').count()) === 1);
    ok('saved runs: no page errors', cerrs.length === 0);
    fs.unlinkSync(tmp);
  }
  console.log('page errors:', JSON.stringify(errs));
  await b.close();
})();
