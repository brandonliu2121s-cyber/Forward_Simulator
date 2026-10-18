// UI smoke test for dashboard/index.html (needs Playwright + Chromium).  Run:  node tests/ui_smoke.js
// Exercises overrides, chart tabs, event chips, keyboard, bars, scenario buttons, activity edits, search, popovers and the pricing stepper.
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ ...(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {}) });
  const pg = await b.newPage({ viewport: { width: 1280, height: 900 } });
  const errs = []; pg.on('pageerror', (e) => errs.push(e.message)); pg.on('console', (m) => m.type() === 'error' && errs.push(m.text()));
  await pg.goto('file://'+require('path').resolve(__dirname,'../dashboard/index.html')); await pg.waitForTimeout(400);
  const txt = (s) => pg.locator(s).first().innerText();
  const ok = (name, cond) => console.log((cond ? 'PASS' : 'FAIL') + '  ' + name);
  const pnl0 = await txt('.left .big');
  // 1. Settings override: spread 5 -> 12 ticks changes P&L and shows override styling
  await pg.click('.nav button:has-text("Settings")');
  await pg.fill('#f-spread_ticks', '12'); await pg.dispatchEvent('#f-spread_ticks', 'change'); await pg.waitForTimeout(200);
  ok('override gets orange class', (await pg.getAttribute('#f-spread_ticks', 'class')) === 'ov');
  await pg.click('.nav button:has-text("Desk")'); await pg.waitForTimeout(200);
  ok('P&L changes after spread override', (await txt('.left .big')) !== pnl0);
  // 2. reset
  await pg.click('.nav button:has-text("Settings")'); await pg.click('button:has-text("Reset to defaults")');
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
  console.log('page errors:', JSON.stringify(errs));
  await b.close();
})();
