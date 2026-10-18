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
  ok('search filters to 1 row', (await pg.locator('tbody tr').count()) === 1);
  await pg.click('tbody tr'); await pg.waitForTimeout(250);
  ok('row click loads WTI on desk', (await txt('.who')).includes('WTI Crude') && (await txt('h2')).includes('Desk Performance'));
  // 10. bell popover + escape
  await pg.click('button[aria-label="Limit alerts"]'); ok('bell popover opens', (await pg.locator('.pop').count()) === 1);
  await pg.keyboard.press('Escape'); ok('Escape closes popover', (await pg.locator('.pop').count()) === 0);
  // 11. pricing stepper
  await pg.click('.nav button:has-text("Pricing")'); await pg.click('button[aria-label="One clip longer"]'); await pg.click('button[aria-label="One clip longer"]');
  ok('stepper to +4 clips (limit) then hedge warning', (await txt('#clipval')).includes('4') && (await pg.locator('main').innerText()).includes('can breach'));
  console.log('page errors:', JSON.stringify(errs));
  await b.close();
})();
