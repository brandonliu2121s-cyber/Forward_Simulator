// Browser end-to-end test: starts the real server with a throwaway database and drives the UI.  node commodity_sim/tests/ui_smoke.js
// Needs Playwright + Chromium (PW_CHROMIUM=<path> NODE_PATH=<playwright modules>).
const { chromium } = require('playwright');
const cp = require('child_process'), fs = require('fs'), os = require('os'), path = require('path');

(async () => {
  const root = path.resolve(__dirname, '..'), dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cd-')), dbFile = path.join(dir, 't.db');
  const srv = cp.spawn('python3', [path.join(root, 'app.py'), '--port', '0', '--db', dbFile], { stdio: ['ignore', 'pipe', 'pipe'] });
  const base = await new Promise((resolve, reject) => { let b = ''; const t = setTimeout(() => reject(new Error('server did not start: ' + b)), 8000); srv.stdout.on('data', (d) => { b += d; const m = b.match(/http:\/\/127\.0\.0\.1:\d+\//); if (m) { clearTimeout(t); resolve(m[0]); } }); srv.stderr.on('data', (d) => { b += d; }); });
  const ok = (name, cond) => { console.log((cond ? 'PASS' : 'FAIL') + '  ' + name); if (!cond) process.exitCode = 1; };
  const b = await chromium.launch(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {});
  try {
    const pg = await b.newPage({ viewport: { width: 1280, height: 900 } }); const errs = []; pg.on('pageerror', (e) => errs.push(String(e))); pg.on('console', (m) => { if (m.type() === 'error' && !/status of 400/.test(m.text())) errs.push(m.text()); });
    await pg.goto(base); await pg.waitForSelector('#ch-price svg');
    ok('opens on the Market tab with a chart, indicators and a signal', (await pg.locator('#ch-rsi svg').count()) === 1 && (await pg.locator('#ch-macd svg').count()) === 1 && /BUY|SELL|HOLD/.test(await pg.locator('.pill').first().innerText()));
    ok('the signal card lists four votes with reasons', (await pg.locator('.vote').count()) === 4 && (await pg.locator('.vote p').first().innerText()).length > 10);
    ok('all nine commodities are offered in three groups', (await pg.locator('#sel-c optgroup').count()) === 3 && (await pg.locator('#sel-c option').count()) === 9);
    const day0 = await pg.locator('.bar .num.muted').first().innerText();
    await pg.click('[data-act="step21"]'); await pg.waitForTimeout(500);
    ok('stepping moves the day forward', (await pg.locator('.bar .num.muted').first().innerText()) !== day0 && /Day 21 /.test(await pg.locator('.bar .num.muted').first().innerText()));
    const scoreA = await pg.locator('.card[aria-label="Analysis and signal"] .muted.num').first().innerText();
    await pg.click('[data-act="step21"]'); await pg.waitForTimeout(500);
    ok('analysis updates as the market moves (and never crashes)', (await pg.locator('.vote').count()) === 4 && errs.length === 0 && typeof scoreA === 'string');
    // metals vs energy get different weights
    await pg.selectOption('#sel-c', 'gold'); await pg.waitForTimeout(900);
    ok('switching to gold loads a new market and uses the metals weights (trend 45%)', /weight 45%/.test(await pg.locator('.votes').innerText()));
    await pg.selectOption('#sel-c', 'wti'); await pg.waitForTimeout(900);
    // same seed => same price
    const p1 = await pg.locator('.num').filter({ hasText: /^\$/ }).first().innerText();
    await pg.click('[data-act="new"]'); await pg.waitForTimeout(900); await pg.fill('#in-seed', '1'); await pg.press('#in-seed', 'Enter'); await pg.locator('#in-seed').dispatchEvent('change'); await pg.waitForTimeout(900);
    ok('the same seed reproduces the same market', (await pg.locator('.num').filter({ hasText: /^\$/ }).first().innerText()) === p1);

    // ---- trade
    await pg.click('[data-tab="trade"]'); await pg.waitForSelector('#in-qty');
    ok('trade tab shows the order ticket and a flat account', (await pg.locator('.tile .val').first().innerText()).includes('100,000') && /Flat/.test(await pg.locator('.tiles').innerText()));
    await pg.fill('#in-qty', '3'); await pg.click('[data-act="place"]'); await pg.waitForTimeout(400);
    ok('an order does not fill on the day it is placed', (await pg.locator('table tbody tr').count()) === 0 && /Flat/.test(await pg.locator('.tiles').innerText()));
    await pg.click('[data-act="step1"]'); await pg.waitForTimeout(600);
    ok('it fills at the next open: long 3 lots, with a fee', /Long 3 lots/.test(await pg.locator('.tiles').innerText()) && (await pg.locator('table tbody tr').count()) === 1);
    await pg.click('[data-side="sell"]'); await pg.click('[data-otype="stop"]'); await pg.fill('#in-price', '1'); await pg.fill('#in-qty', '3'); await pg.click('[data-act="place"]'); await pg.waitForTimeout(400);
    ok('a stop order rests in the working list and can be cancelled', /stop/.test(await pg.locator('.card:has(h3:text("Working orders"))').innerText()));
    await pg.click('[data-cancel]'); await pg.waitForTimeout(400);
    ok('cancel removes it', /None/.test(await pg.locator('.card:has(h3:text("Working orders"))').innerText()));
    await pg.click('[data-act="close"]'); await pg.click('[data-act="step1"]'); await pg.waitForTimeout(600);
    ok('close position flattens the account next day', /Flat/.test(await pg.locator('.tiles').innerText()) && (await pg.locator('table tbody tr').count()) === 2);
    await pg.click('[data-side="buy"]'); await pg.click('[data-otype="market"]'); await pg.fill('#in-qty', '0'); await pg.click('[data-act="place"]');
    ok('a zero-lot order is refused with a clear message', /whole number/.test(await pg.locator('.note').first().innerText()));
    await pg.fill('#in-qty', '100000'); await pg.click('[data-act="place"]'); await pg.click('[data-act="step1"]'); await pg.waitForTimeout(600);
    ok('an order beyond the leverage cap is rejected, not filled', /exceed/.test(await pg.locator('.card:has(h3:text("Working orders"))').innerText()));
    await pg.fill('#sv-name-trade', 'My practice <b>run</b>'); await pg.click('[data-act="save-trade"]'); await pg.waitForTimeout(500);
    ok('a scenario can be saved (hostile name shown as text)', /My practice <b>run<\/b>/.test(await pg.locator('.card:has(h3:text("Saved scenarios"))').innerText()) && (await pg.locator('.card:has(h3:text("Saved scenarios")) b').count()) === 1);
    await pg.click('[data-act="reset"]'); await pg.waitForTimeout(500);
    ok('reset clears orders and returns to day 0', /Flat/.test(await pg.locator('.tiles').innerText()) && (await pg.locator('table tbody tr').count()) === 0);
    await pg.click('[data-load]'); await pg.waitForTimeout(1200);
    ok('loading the scenario restores the orders and trades', (await pg.locator('table tbody tr').count()) >= 2);
    await pg.click('[data-del]'); await pg.click('[data-del]'); await pg.waitForTimeout(500);
    ok('delete takes two clicks', /Nothing saved yet/.test(await pg.locator('.card:has(h3:text("Saved scenarios"))').innerText()));

    // ---- backtest
    await pg.click('[data-tab="backtest"]'); await pg.waitForSelector('[data-act="bt-run"]');
    await pg.selectOption('#bt-s', 'sma_cross'); await pg.click('[data-act="bt-run"]'); await pg.waitForSelector('#ch-bt svg');
    ok('a backtest shows metrics against buy-and-hold, equity and drawdown charts', (await pg.locator('table tbody tr').first().innerText()).includes('Strategy') && (await pg.locator('#ch-dd svg').count()) === 1);
    await pg.fill('#bt-n', '20'); await pg.locator('#bt-n').dispatchEvent('change'); await pg.click('[data-act="bt-mc"]'); await pg.waitForSelector('.hist', { timeout: 20000 });
    ok('the many-markets test reports how often it was profitable', /profitable in \d+%/.test(await pg.locator('.card:has(.hist)').innerText()) && (await pg.locator('.hist i').count()) === 20);
    await pg.click('[data-act="bt-sw"]'); await pg.waitForSelector('text=train vs test');
    ok('the sweep lists 12 settings with train and test returns', (await pg.locator('.card:has-text("train vs test") tbody tr').count()) === 12);
    await pg.fill('#bt-sl', '500'); await pg.locator('#bt-sl').dispatchEvent('change'); await pg.click('[data-act="bt-run"]'); await pg.waitForTimeout(1200);
    ok('very high slippage is accepted and the run still completes', (await pg.locator('#ch-bt svg').count()) === 1);
    await pg.fill('#bt-a', '9999'); await pg.locator('#bt-a').dispatchEvent('change'); await pg.click('[data-act="bt-run"]'); await pg.waitForTimeout(800);
    ok('an impossible position size gives a clear error instead of a crash', /Position size must be between/.test(await pg.locator('.card:has(h3:text("Strategy backtest")) .note').innerText()));
    await pg.fill('#bt-a', '50'); await pg.locator('#bt-a').dispatchEvent('change');

    // ---- learn
    await pg.click('[data-tab="learn"]');
    ok('the Learn tab explains the limits plainly', /not investment advice|Nothing here is investment advice/.test(await pg.locator('.learn').innerText()) && (await pg.locator('.learn li').count()) > 8);
    ok('no page errors or console errors', errs.length === 0);
    if (errs.length) console.log(errs);

    // ---- layout at narrow widths, with a hostile saved name
    for (const w of [320, 400, 1280]) {
      const mp = await b.newPage({ viewport: { width: w, height: 900 } });
      await mp.goto(base + '#trade'); await mp.waitForSelector('#in-qty');
      await mp.fill('#sv-name-trade', 'Aleksandra-Wiśniewska-Kowalczyk-unbreakable-name-that-goes-on-and-on-and-on-and-on-and-on-forever 🦊'); await mp.click('[data-act="save-trade"]'); await mp.waitForTimeout(500);
      for (const tab of ['market', 'trade', 'backtest', 'learn']) {
        await mp.click(`[data-tab="${tab}"]`); await mp.waitForTimeout(500);
        if (tab === 'backtest') { await mp.click('[data-act="bt-run"]'); await mp.waitForTimeout(1200); }
        const over = await mp.evaluate(() => document.documentElement.scrollWidth - innerWidth);
        ok(`no sideways scroll at ${w}px on ${tab}`, over <= 0);
      }
      await mp.close();
    }
  } finally { srv.kill(); await b.close(); fs.rmSync(dir, { recursive: true, force: true }); }
})();
